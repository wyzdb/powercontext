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

"""Complete physical PDF pages and offline retrieval of exact Memory evidence.

Parsing never depends on a question. Retrieval reads only the supplied scoped
Memory; it requires neither the original file nor an auxiliary persistent index.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import zlib
from collections import Counter
from itertools import pairwise
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from powercontext.artifacts import MemoryCitation
from powercontext.builtin.artifacts.memory.models import MemoryHit
from powercontext.builtin.runtime.models import (
    GetMemoryEntryRequest,
    MemoryEntryRecord,
    MemorySearchPage,
    SearchMemoryRequest,
)
from powercontext.sources import AdapterSourceDefinition
from powercontext.sources.models import Source, SourceMaterialization
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY, TextEvidence

if TYPE_CHECKING:
    from pypdf.generic import DictionaryObject, StreamObject


class PDFDocumentInput(BaseModel):
    """Original PDF bytes and caller-owned document identity."""

    model_config = ConfigDict(frozen=True)

    document_id: str
    content: bytes

    @field_validator("document_id")
    @classmethod
    def require_document_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("document_id must not be blank")  # noqa: TRY003
        return value


class PDFPageInput(BaseModel):
    """Extracted text anchored to one physical page of an exact PDF revision."""

    model_config = ConfigDict(frozen=True)

    document_id: str
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_number: int = Field(ge=1, strict=True)
    text: str

    @field_validator("document_id")
    @classmethod
    def require_document_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("document_id must not be blank")  # noqa: TRY003
        return value


def _validate_flate_stream(stream: StreamObject) -> None:
    """Reject truncated/corrupt zlib data that pypdf recovers as partial text."""
    from pypdf.filters import decode_stream_data
    from pypdf.generic import ArrayObject, DictionaryObject, EncodedStreamObject, NameObject, NullObject

    value = stream.get("/Filter")
    if value is None:
        return
    value = value.get_object()
    filters = tuple(name.get_object() for name in value) if isinstance(value, ArrayObject) else (value,)
    if not any(name in {"/FlateDecode", "/Fl"} for name in filters):
        return
    params = stream.get("/DecodeParms")
    if params is not None:
        params = params.get_object()
    if params is None or isinstance(params, NullObject):
        parameters = (DictionaryObject(),) * len(filters)
    elif isinstance(params, ArrayObject):
        parameters = tuple(params)
    else:
        parameters = (params,)
    if len(parameters) != len(filters):
        raise ValueError("PDF content filters and parameters do not match")  # noqa: TRY003
    # pypdf's public get_data() deliberately repairs malformed compression. The
    # pinned StreamObject stores the original encoded bytes in _data; checking
    # these bytes is necessary before that recovery discards the failure.
    data = stream._data
    for name, parameter in zip(filters, parameters, strict=True):
        if name in {"/FlateDecode", "/Fl"}:
            decoder = zlib.decompressobj()
            decoder.decompress(data)
            decoder.flush()
            if not decoder.eof:
                raise ValueError("PDF content has an incomplete Flate stream")  # noqa: TRY003
        stage = EncodedStreamObject()
        stage.update(stream)
        stage[NameObject("/Filter")] = name
        stage[NameObject("/DecodeParms")] = parameter.get_object()
        stage._data = data
        data = decode_stream_data(stage)


def _validate_form_streams(resources: DictionaryObject, seen: set[int]) -> None:
    """Validate compressed text in nested Form XObjects, excluding images."""
    from pypdf.generic import DictionaryObject, NullObject, StreamObject

    objects = resources.get("/XObject")
    if objects is None or isinstance(objects.get_object(), NullObject):
        return
    for reference in objects.get_object().values():
        form = reference.get_object()
        if not isinstance(form, DictionaryObject) or form.get("/Subtype") != "/Form" or id(form) in seen:
            continue
        seen.add(id(form))
        if not isinstance(form, StreamObject):
            raise TypeError("PDF Form is not a content stream")  # noqa: TRY003
        _validate_flate_stream(form)
        nested = form.get("/Resources")
        if nested is not None and isinstance(nested.get_object(), DictionaryObject):
            _validate_form_streams(nested.get_object(), seen)


def parse_pdf_document(value: PDFDocumentInput) -> tuple[PDFPageInput, ...]:
    """Extract every page, returning nothing if any page cannot be decoded.

    Plain extraction preserves pypdf's text and number tokens without layout
    synthesis, cross-page joins, truncation, or query-dependent filtering.
    """
    from pypdf import PdfReader
    from pypdf.generic import ArrayObject, DictionaryObject, NullObject, StreamObject

    digest = hashlib.sha256(value.content).hexdigest()
    try:
        reader = PdfReader(io.BytesIO(value.content), strict=True)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("PDF requires a non-empty password")  # noqa: TRY003, TRY301
        extracted = []
        for number, page in enumerate(reader.pages, start=1):
            # pypdf tolerates non-stream /Contents array members by dropping
            # them with a warning. Such a page is corrupt, not a blank page.
            contents = page.get("/Contents")
            if contents is not None:
                contents = contents.get_object()
                streams = (
                    contents
                    if isinstance(contents, ArrayObject)
                    else (() if isinstance(contents, NullObject) else (contents,))
                )
                if any(not isinstance(stream.get_object(), StreamObject) for stream in streams):
                    raise ValueError("PDF page has an invalid content stream")  # noqa: TRY003, TRY301
                for stream in streams:
                    _validate_flate_stream(stream.get_object())
            resources = page.get("/Resources")
            if resources is not None and isinstance(resources.get_object(), DictionaryObject):
                _validate_form_streams(resources.get_object(), set())
            extracted.append(
                PDFPageInput(
                    document_id=value.document_id,
                    document_sha256=digest,
                    page_number=number,
                    text=page.extract_text() or "",
                )
            )
        pages = tuple(extracted)
        if not pages:
            raise ValueError("PDF has no physical pages")  # noqa: TRY003, TRY301
    except Exception as error:
        # pypdf can raise parser, codec, encryption, or stream errors lazily on
        # later pages. Normalize at the document boundary, after eager extraction.
        raise ValueError("PDF could not be completely parsed") from error  # noqa: TRY003
    return pages


class PDFPageSource(Source):
    """Captured page data, sufficient for readback without reopening a file."""

    page: PDFPageInput


class PDFPageAdapter:
    input_class = PDFPageInput
    name = "pdf-page"
    source_class = PDFPageSource

    async def resolve(self, value: PDFPageInput, /) -> PDFPageSource:
        # Canonical framing prevents delimiter collisions in arbitrary document
        # IDs; fixed-size digests keep even very long IDs below the Source limit.
        identity = json.dumps(
            [value.document_id, value.document_sha256, value.page_number], ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        return PDFPageSource(
            name=f"pdf-page:{hashlib.sha256(identity).hexdigest()}",
            materialization=SourceMaterialization.CAPTURED,
            page=value,
        )

    async def read(self, source: PDFPageSource, /) -> PDFPageInput:
        return source.page


class PDFPageTextProjection:
    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PDFPageSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PDFPageSource, /) -> TextEvidence:
        page = source.page
        return TextEvidence(
            source_type="pdf-page",
            source_id=source.name,
            content=f"{page.document_id}\n{page.text}",
            metadata={
                "document_id": page.document_id,
                "document_sha256": page.document_sha256,
                "page_number": page.page_number,
            },
        )


PDF_PAGE_SOURCE_DEFINITION = AdapterSourceDefinition(PDFPageAdapter(), projections=(PDFPageTextProjection(),))


class _ScopedMemory(Protocol):
    async def search(self, request: SearchMemoryRequest, /) -> MemorySearchPage: ...

    async def get(self, request: GetMemoryEntryRequest, /) -> MemoryEntryRecord: ...


_WORDS = re.compile(r"[a-z]+|\d+")
_STOP_WORDS = frozenset([
    "a",
    "an",
    "the",
    "and",
    "or",
    "for",
    "of",
    "to",
    "in",
    "on",
    "at",
    "by",
    "from",
    "with",
    "as",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "what",
    "which",
    "who",
    "how",
    "why",
    "when",
    "where",
    "do",
    "does",
    "did",
    "can",
    "could",
    "should",
    "would",
    "has",
    "have",
    "had",
    "i",
    "we",
    "you",
    "it",
    "its",
    "s",
    "our",
    "your",
    "this",
    "that",
    "these",
    "those",
    "please",
    "any",
    "than",
    "then",
    "if",
    "not",
    "only",
    "give",
    "answer",
    "respond",
    "response",
    "question",
    "assuming",
    "assume",
    "perspective",
    "investment",
    "analyst",
    "use",
    "using",
    "used",
    "shown",
    "details",
    "within",
    "based",
    "relying",
    "define",
    "calculate",
    "state",
    "explicitly",
    "directly",
    "outlined",
    "reported",
    "important",
    "materially",
    "fy",
    "fiscal",
    "year",
    "years",
    "usd",
    "million",
    "millions",
])
# General financial vocabulary, independent of companies, files, and benchmarks.
# Each small query avoids requiring an entire verbose question on one page.
_CONCEPTS = (
    (
        frozenset({"geography", "geographies", "geographic", "operates", "regions", "countries"}),
        "geographic segments divisions countries international operations",
    ),
    (
        frozenset({"legal", "litigation", "lawsuit", "lawsuits", "battles"}),
        "legal proceedings litigation contingencies lawsuits",
    ),
    (frozenset({"restructuring", "reorganization"}), "restructuring charges costs income earnings statement"),
    (
        frozenset({"ebitda", "depreciation", "amortization", "capex", "cash"}),
        "cash flows depreciation amortization capital expenditures",
    ),
    (
        frozenset({"income", "earnings", "profit", "ebitda", "margin"}),
        "consolidated income earnings operations revenue sales operating profit",
    ),
    (
        frozenset({"assets", "liabilities", "equity", "balance", "debt"}),
        "consolidated balance sheets assets liabilities equity debt",
    ),
    (
        frozenset({"dividend", "dividends", "repurchases", "buybacks"}),
        "dividends repurchases common stock shareholders",
    ),
)


def _terms(text: str) -> list[str]:
    return _WORDS.findall(text.lower())


def _stem(term: str) -> str:
    if len(term) > 5 and term.endswith("ies"):
        return term[:-3] + "y"
    if len(term) > 4 and term.endswith("s") and not term.endswith("ss"):
        return term[:-1]
    return term


def _heading_score(body: str, question_words: set[str]) -> float:
    """Prefer the primary statement or disclosure named in a financial question.

    Mentions in the body of an exhibit should not outrank a short primary
    disclosure merely because the exhibit repeats more of the query words.
    """
    headings = [" ".join(_terms(line)) for line in body.splitlines() if 0 < len(_terms(line)) <= 12]
    score = 0.0
    groups = (
        (
            {"income", "earnings", "profit", "ebitda", "margin"},
            (
                "statement of income",
                "statements of income",
                "statement of earnings",
                "statements of earnings",
                "statement of operations",
                "statements of operations",
                "income statement",
                "income statements",
            ),
        ),
        (
            {"cash", "flows", "ebitda", "capex", "depreciation", "amortization"},
            ("statement of cash flows", "statements of cash flows"),
        ),
        (
            {"assets", "liabilities", "equity", "balance", "debt"},
            ("balance sheet", "balance sheets", "statement of financial position", "statements of financial position"),
        ),
        (
            {"legal", "litigation", "lawsuit", "lawsuits", "battles"},
            ("legal proceedings", "litigation", "commitments and contingencies"),
        ),
        (
            {"geography", "geographies", "geographic", "regions", "countries", "operates"},
            ("our divisions", "reportable segments", "geographic information", "geographical information"),
        ),
    )
    for triggers, titles in groups:
        if question_words & triggers and any(title in heading for title in titles for heading in headings):
            score += 12
    return score


def _rank_pages(hits: list[MemoryHit], question: str, concepts: list[str]) -> list[MemoryHit]:
    """BM25 over the bounded candidate union, with document and phrase signals."""
    query = list(dict.fromkeys(term for term in _terms(question) if term not in _STOP_WORDS))
    weights = {_stem(term): 1.0 for term in query}
    for concept in concepts:
        for term in _terms(concept):
            weights.setdefault(_stem(term), 0.55)
    bodies = [hit.text.partition("\n")[2] for hit in hits]
    counts = [Counter(_stem(term) for term in _terms(body)) for body in bodies]
    frequencies: Counter[str] = Counter()
    for count in counts:
        frequencies.update(count.keys())
    average_length = sum(count.total() for count in counts) / max(1, len(counts)) or 1
    question_words = set(_terms(question))
    question_years = set(re.findall(r"(?:19|20)\d{2}", question))
    scores = []
    phrases = list(pairwise(query))
    for hit, body, count in zip(hits, bodies, counts, strict=True):
        length = count.total()
        score = 0.0
        for term, weight in weights.items():
            frequency = count[term]
            idf = math.log(1 + (len(hits) - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
            score += weight * idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * length / average_length))
        normalized = " ".join(_terms(body))
        score += sum(0.8 for left, right in phrases if f"{left} {right}" in normalized)
        score += _heading_score(body, question_words)
        # The projection's first line is the caller's document ID, not a page
        # header guessed from the PDF. Prefer the requested company and revision.
        document_words = set(_terms(hit.text.partition("\n")[0]))
        names = {
            term for term in document_words if len(term) > 2 and term not in {"annual", "report"} and term.isalpha()
        }
        if names & question_words:
            score = score * 1.8 + 3
        document_years = document_words & question_years
        if question_years and document_years:
            score *= 1.15
        scores.append((score, hit))
    scores.sort(key=lambda item: (-item[0], item[1].entry_id, item[1].entry_version_id))
    return [hit for _, hit in scores]


async def search_pdf_pages(memory: _ScopedMemory, question: str, limit: int = 10) -> tuple[MemoryCitation, ...]:
    """Retrieve distinct PDF pages using public scoped Memory APIs only.

    Candidate pools are bounded (at most fourteen searches, 512 hits each). All
    scoring is request-local. Citations preserve the exact revision and entry
    version supplied by Memory, including after reopening the Runtime.
    """
    if limit <= 0 or not question.strip():
        return ()
    words = set(_terms(question))
    terms = list(dict.fromkeys(term for term in _terms(question) if term not in _STOP_WORDS))
    if not terms:
        return ()
    concepts = [text for triggers, text in _CONCEPTS if words & triggers]
    queries = [" ".join(terms), *concepts]
    # Narrow lexical subqueries preserve candidates otherwise lost to Memory's
    # minimum query coverage rule on long, instruction-heavy questions.
    queries.extend(" ".join(terms[offset : offset + 2]) for offset in range(0, min(len(terms), 12), 2))
    pool: dict[tuple[str, str, str], MemoryHit] = {}
    for query in dict.fromkeys(queries):
        result = await memory.search(SearchMemoryRequest(query=query, mode="fts", limit=min(512, max(160, limit * 8))))
        for hit in result.hits:
            pool.setdefault((hit.memory_ref.artifact_id, hit.entry_id, hit.entry_version_id), hit)
    ranked = _rank_pages(list(pool.values()), question, concepts)
    citations = []
    seen_pages: set[tuple[str, str]] = set()
    for hit in ranked:
        citation = MemoryCitation(
            memory_ref=hit.memory_ref, entry_id=hit.entry_id, entry_version_id=hit.entry_version_id
        )
        record = await memory.get(GetMemoryEntryRequest(citation=citation))
        pages = {
            (source.source_type, source.source_id)
            for source in record.entry.sources
            if source.source_type == "pdf-page"
        }
        # Fixed page projections contain one Source. Ignore unrelated or combined
        # entries rather than returning a citation that ambiguously names pages.
        if len(pages) != 1 or pages & seen_pages:
            continue
        seen_pages.update(pages)
        citations.append(citation)
        if len(citations) == limit:
            break
    return tuple(citations)
