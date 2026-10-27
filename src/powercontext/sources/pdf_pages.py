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

"""PDF page Sources and citation lookup for complete financial reports."""

from __future__ import annotations

import hashlib
import io
import re
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader

from powercontext.builtin.artifacts.memory import MemoryCitation
from powercontext.builtin.runtime.models import SearchMemoryRequest
from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import (
    TEXT_EVIDENCE_PROJECTION_KEY,
    AdapterSourceDefinition,
    Source,
    SourceMaterialization,
    TextEvidence,
)

PDF_PAGE_SOURCE_NAME = "pdf-page"
PDF_PAGE_SOURCE_VERSION = "1"


class PDFDocumentInput(BaseModel):
    """One complete PDF document to split into physical pages."""

    model_config = ConfigDict(frozen=True)

    document_id: str
    content: bytes


class PDFPageInput(BaseModel):
    """One physical PDF page and its extracted text."""

    model_config = ConfigDict(frozen=True)

    document_id: str
    document_sha256: str
    page_number: int = Field(ge=1)
    text: str


class PDFPageSource(Source):
    """Captured evidence for exactly one physical PDF page."""

    source_id: str
    document_id: str
    document_sha256: str
    page_number: int
    text: str


def pdf_page_source_id(document_id: str, document_sha256: str, page_number: int, /) -> str:
    """Build the stable identity for one page of one PDF revision."""

    _validate_document_id(document_id)
    _validate_sha256(document_sha256)
    if type(page_number) is not int or page_number < 1:
        raise ValueError("page_number must be a positive integer")
    source_id = f"pdf:{quote(document_id, safe='')}:{document_sha256}:{page_number}"
    if len(source_id) > MAX_SOURCE_ID_LENGTH:
        raise ValueError(f"pdf-page source_id must not exceed {MAX_SOURCE_ID_LENGTH} characters")
    return source_id


def parse_pdf_document(value: PDFDocumentInput, /) -> tuple[PDFPageInput, ...]:
    """Extract every physical page from one complete PDF or fail atomically."""

    _validate_document_id(value.document_id)
    if not isinstance(value.content, bytes) or not value.content:
        raise ValueError("PDF content must be non-empty bytes")
    document_sha256 = hashlib.sha256(value.content).hexdigest()

    try:
        reader = PdfReader(io.BytesIO(value.content), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("PDF requires a non-empty password")
        page_count = len(reader.pages)
        if page_count < 1:
            raise ValueError("PDF must contain at least one physical page")
        pages = tuple(
            PDFPageInput(
                document_id=value.document_id,
                document_sha256=document_sha256,
                page_number=index,
                text=reader.pages[index - 1].extract_text() or "",
            )
            for index in range(1, page_count + 1)
        )
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("PDF could not be parsed completely") from error
    return pages


class PDFPageSourceAdapter:
    """Resolve and read the captured PDF page Source."""

    input_class = PDFPageInput
    name = PDF_PAGE_SOURCE_NAME
    source_class = PDFPageSource

    async def resolve(self, value: PDFPageInput, /) -> PDFPageSource:
        source_id = pdf_page_source_id(value.document_id, value.document_sha256, value.page_number)
        return PDFPageSource(
            name=source_id,
            source_id=source_id,
            materialization=SourceMaterialization.CAPTURED,
            document_id=value.document_id,
            document_sha256=value.document_sha256,
            page_number=value.page_number,
            text=value.text,
        )

    async def read(self, source: PDFPageSource, /) -> PDFPageInput:
        return PDFPageInput(
            document_id=source.document_id,
            document_sha256=source.document_sha256,
            page_number=source.page_number,
            text=source.text,
        )


class PDFPageTextEvidenceProjection:
    """Expose one PDF page as the standard text evidence."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PDFPageSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PDFPageSource, /) -> TextEvidence:
        return TextEvidence(
            source_type=PDF_PAGE_SOURCE_NAME,
            source_id=source.source_id,
            content=f"{source.document_id}\n{source.text}",
            metadata={
                "document_id": source.document_id,
                "document_sha256": source.document_sha256,
                "page_number": source.page_number,
            },
        )


PDF_PAGE_SOURCE_ADAPTER = PDFPageSourceAdapter()
PDF_PAGE_SOURCE_DEFINITION = AdapterSourceDefinition(
    PDF_PAGE_SOURCE_ADAPTER,
    version=PDF_PAGE_SOURCE_VERSION,
    projections=(PDFPageTextEvidenceProjection(),),
)


async def search_pdf_pages(
    memory: Any,
    question: str,
    limit: int = 10,
) -> tuple[MemoryCitation, ...]:
    """Return up to limit distinct, exactly resolvable page citations."""

    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be non-empty")
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be a positive integer")

    best: dict[tuple[str, str], tuple[float, int, Any]] = {}
    order = 0
    for query in _search_queries(question):
        result = await memory.search(SearchMemoryRequest(query=query, limit=100, mode="fts"))
        for hit in result.hits:
            key = (hit.entry_id, hit.entry_version_id)
            score = float(hit.score) if hit.score is not None else 0.0
            existing = best.get(key)
            if existing is None or score > existing[0]:
                best[key] = (score, order, hit)
            order += 1

    ranked = sorted(best.values(), key=lambda item: (-item[0], item[1]))[:100]
    citations = [
        MemoryCitation(
            memory_ref=hit.memory_ref,
            entry_id=hit.entry_id,
            entry_version_id=hit.entry_version_id,
        )
        for _score, _order, hit in ranked
    ]
    pages, page_citations = await _page_map(memory)
    if not pages:
        return tuple(citations[:limit])

    candidates: dict[int, tuple[float, int, MemoryCitation]] = {}
    for rank, citation in enumerate(citations):
        page = pages.get((citation.entry_id, citation.entry_version_id))
        if page is None:
            continue
        base = 1.0 / ((rank + 1) ** 0.7)
        for delta, weight in ((0, 1.0), (1, 1.0), (-1, 1.0), (2, 0.6), (-2, 0.6)):
            neighbor = page + delta
            neighbor_citation = page_citations.get(neighbor)
            if neighbor_citation is None:
                continue
            score = base * weight
            existing = candidates.get(neighbor)
            if existing is None or score > existing[0]:
                candidates[neighbor] = (score, rank, neighbor_citation)

    selected = sorted(candidates.values(), key=lambda item: (-item[0], item[1]))[:limit]
    return tuple(item[2] for item in selected)


async def _page_map(
    memory: Any,
) -> tuple[
    dict[tuple[str, str], int],
    dict[int, MemoryCitation],
]:
    """Map Memory citations to physical PDF pages through their Source identities."""

    cached = getattr(memory, "_pdf_page_citation_map", None)
    if cached is not None:
        return cached
    entries = await memory.list()
    by_citation: dict[tuple[str, str], int] = {}
    by_page: dict[int, MemoryCitation] = {}
    for record in entries.entries:
        citation = MemoryCitation(
            memory_ref=record.memory_ref,
            entry_id=record.entry.entry_id,
            entry_version_id=record.entry.entry_version_id,
        )
        page = None
        for reference in record.entry.sources:
            if reference.source_type != PDF_PAGE_SOURCE_NAME:
                continue
            try:
                page = int(reference.source_id.rsplit(":", 1)[-1])
            except ValueError:
                continue
            break
        if page is None:
            continue
        by_citation[(citation.entry_id, citation.entry_version_id)] = page
        by_page[page] = citation
    setattr(memory, "_pdf_page_citation_map", (by_citation, by_page))
    return by_citation, by_page


_STOPWORDS = frozenset(
    {
        "a",
        "about",
        "after",
        "all",
        "also",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "may",
        "must",
        "not",
        "of",
        "on",
        "or",
        "should",
        "such",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "to",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "whose",
        "will",
        "with",
        "would",
    }
)


def _search_queries(question: str):
    yield question
    keywords: list[str] = []
    for word in re.findall(r"[a-z0-9]+", question.casefold()):
        if len(word) >= 3 and word not in _STOPWORDS and word not in keywords:
            keywords.append(word)
        if len(keywords) == 12:
            break
    if keywords:
        keyword_query = " ".join(keywords)
        if keyword_query != question:
            yield keyword_query
    expansions: list[str] = []
    for word in keywords:
        for prefix, phrases in _QUERY_EXPANSIONS:
            if word.startswith(prefix):
                for phrase in phrases:
                    if phrase not in expansions:
                        expansions.append(phrase)
    for phrase in expansions:
        if phrase != question and phrase != " ".join(keywords):
            yield phrase


_QUERY_EXPANSIONS = (
    ("geograph", ("countries and territories", "segments operations")),
    ("legal", ("legal proceedings", "litigation contingencies")),
    ("battle", ("legal proceedings", "litigation contingencies")),
    ("litigation", ("legal proceedings", "litigation contingencies")),
    ("restructur", ("restructuring charges", "restructuring costs")),
    ("ebitda", ("income statement operating income", "cash flows depreciation amortization")),
    ("income", ("consolidated statement of income", "consolidated statements of income", "income statement operating income", "statements of income")),
    ("margin", ("operating income net revenue",)),
    ("revenue", ("net revenue net sales",)),
    ("sales", ("net sales net revenue",)),
    ("operating", ("operating income operating profit",)),
    ("profit", ("operating profit net income",)),
    ("cash", ("cash flows operating activities", "free cash flow")),
    ("asset", ("total assets current assets",)),
    ("liabilit", ("total liabilities current liabilities",)),
    ("equity", ("shareholders equity total equity",)),
    ("employee", ("employees headcount",)),
    ("segment", ("reportable segments geographic segments",)),
    ("dividend", ("dividends share repurchases",)),
    ("risk", ("risk factors uncertainties",)),
    ("liquidity", ("liquidity capital resources",)),
)


def _validate_document_id(document_id: str) -> None:
    if not isinstance(document_id, str) or not document_id.strip():
        raise ValueError("document_id must be a non-empty string")


def _validate_sha256(value: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("document_sha256 must be a lowercase SHA-256 hex string")


__all__ = [
    "PDF_PAGE_SOURCE_ADAPTER",
    "PDF_PAGE_SOURCE_DEFINITION",
    "PDF_PAGE_SOURCE_NAME",
    "PDF_PAGE_SOURCE_VERSION",
    "PDFDocumentInput",
    "PDFPageInput",
    "PDFPageSource",
    "PDFPageSourceAdapter",
    "PDFPageTextEvidenceProjection",
    "parse_pdf_document",
    "pdf_page_source_id",
    "search_pdf_pages",
]
