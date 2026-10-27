# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Concurrent Embedding request coalescing with a bounded successful-vector cache."""

from __future__ import annotations

import asyncio
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any

from powercontext.builtin.inference.models import EmbeddingResult, InferenceUsage


@dataclass(frozen=True, slots=True)
class _Request:
    texts: tuple[str, ...]
    future: asyncio.Future[EmbeddingResult]


class CoalescingEmbeddingModel:
    """Share concurrent text batches and reuse successful vectors across calls."""

    def __init__(
        self,
        model: Any,
        *,
        max_batch_size: int = 64,
        coalesce_ms: float = 5.0,
        cache_size: int = 1024,
    ) -> None:
        if type(max_batch_size) is not int or max_batch_size < 1:
            raise ValueError("max_batch_size must be a positive integer")
        if isinstance(coalesce_ms, bool) or not isinstance(coalesce_ms, (int, float)) or coalesce_ms < 0:
            raise ValueError("coalesce_ms must be a non-negative number")
        if type(cache_size) is not int or cache_size < 0:
            raise ValueError("cache_size must be a non-negative integer")
        self.profile = model.profile
        self._model = model
        self._max_batch_size = max_batch_size
        self._coalesce_seconds = float(coalesce_ms) / 1000.0
        self._cache_size = cache_size
        self._cache: OrderedDict[str, tuple[float, ...]] = OrderedDict()
        self._inflight: dict[str, asyncio.Future[tuple[tuple[float, ...], InferenceUsage, object]]] = {}
        self._requests: deque[_Request] = deque()
        self._dispatcher: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[Any]] = set()

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        normalized = tuple(texts)
        if any(not isinstance(text, str) for text in normalized):
            raise ValueError("embedding texts must be strings")
        if not normalized:
            return EmbeddingResult(vectors=(), usage=InferenceUsage(requests=0))

        request = _Request(normalized, asyncio.get_running_loop().create_future())
        self._requests.append(request)
        if self._dispatcher is None or self._dispatcher.done():
            self._dispatcher = asyncio.create_task(self._dispatch(), name="embedding-coalescer")
        return await request.future

    async def _dispatch(self) -> None:
        try:
            while self._requests:
                await asyncio.sleep(self._coalesce_seconds)
                requests: list[_Request] = []
                while self._requests:
                    requests.append(self._requests.popleft())
                if requests:
                    self._start(requests)
        except Exception as error:
            while self._requests:
                request = self._requests.popleft()
                if not request.future.done():
                    request.future.set_exception(error)
        finally:
            self._dispatcher = None

    def _start(self, requests: list[_Request]) -> None:
        loop = asyncio.get_running_loop()
        text_futures: dict[str, asyncio.Future[tuple[tuple[float, ...], InferenceUsage, object]]] = {}
        new_texts: list[str] = []
        for request in requests:
            for text in request.texts:
                if text in self._cache:
                    self._cache.move_to_end(text)
                    continue
                future = self._inflight.get(text)
                if future is None and text not in text_futures:
                    future = loop.create_future()
                    text_futures[text] = future
                    new_texts.append(text)
                elif future is not None:
                    text_futures[text] = future

        for start in range(0, len(new_texts), self._max_batch_size):
            batch = new_texts[start : start + self._max_batch_size]
            futures = [text_futures[text] for text in batch]
            for text in batch:
                self._inflight[text] = text_futures[text]
            task = asyncio.create_task(self._run_batch(batch, futures), name="embedding-batch")
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        for request in requests:
            mapping: dict[str, tuple[float, ...] | asyncio.Future[tuple[tuple[float, ...], InferenceUsage, object]]] = {}
            for text in request.texts:
                if text in self._cache:
                    mapping[text] = self._cache[text]
                else:
                    mapping[text] = text_futures[text]
            task = asyncio.create_task(self._resolve(request, mapping), name="embedding-waiter")
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _run_batch(
        self,
        texts: list[str],
        futures: list[asyncio.Future[tuple[tuple[float, ...], InferenceUsage, object]]],
    ) -> None:
        token = object()
        try:
            result = await self._model.embed(tuple(texts))
            if len(result.vectors) != len(texts):
                raise ValueError("embedding provider returned the wrong number of vectors")
            usage = result.usage if result.usage is not None else InferenceUsage(requests=0)
            for text, vector, future in zip(texts, result.vectors, futures, strict=True):
                if self._cache_size > 0:
                    self._cache[text] = tuple(vector)
                    self._cache.move_to_end(text)
                    while len(self._cache) > self._cache_size:
                        self._cache.popitem(last=False)
                self._inflight.pop(text, None)
                if not future.done():
                    future.set_result((tuple(vector), usage, token))
        except BaseException as error:
            for text, future in zip(texts, futures, strict=True):
                self._inflight.pop(text, None)
                if not future.done():
                    future.set_exception(error)

    async def _resolve(
        self,
        request: _Request,
        mapping: dict[
            str,
            tuple[float, ...] | asyncio.Future[tuple[tuple[float, ...], InferenceUsage, object]],
        ],
    ) -> None:
        try:
            vectors: list[tuple[float, ...]] = []
            usages: dict[int, InferenceUsage] = {}
            for text in request.texts:
                source = mapping[text]
                if isinstance(source, asyncio.Future):
                    vector, usage, token = await asyncio.shield(source)
                    vectors.append(vector)
                    usages[id(token)] = usage
                else:
                    vectors.append(source)
            if not request.future.done():
                request.future.set_result(
                    EmbeddingResult(vectors=tuple(vectors), usage=_sum_usage(tuple(usages.values())))
                )
        except BaseException as error:
            if not request.future.done():
                request.future.set_exception(error)


def _sum_usage(usages: tuple[InferenceUsage, ...]) -> InferenceUsage:
    if not usages:
        return InferenceUsage(requests=0)
    input_tokens = None if any(usage.input_tokens is None for usage in usages) else sum(
        usage.input_tokens or 0 for usage in usages
    )
    output_tokens = None if any(usage.output_tokens is None for usage in usages) else sum(
        usage.output_tokens or 0 for usage in usages
    )
    return InferenceUsage(
        requests=sum(usage.requests for usage in usages),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


__all__ = ["CoalescingEmbeddingModel"]
