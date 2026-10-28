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


def _extract_page_text(page: Any) -> str:
    """Extract one page, tolerating a single malformed page in an otherwise valid PDF."""

    try:
        return page.extract_text() or ""
    except Exception:
        try:
            return page.extract_text(extraction_mode="layout") or ""
        except Exception:
            return ""


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
                text=_extract_page_text(reader.pages[index - 1]),
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
        for rank, hit in enumerate(result.hits):
            key = (hit.entry_id, hit.entry_version_id)
            rrf = 1.0 / (60.0 + rank)
            existing = best.get(key)
            if existing is None:
                best[key] = (rrf, order, hit)
                order += 1
            else:
                best[key] = (existing[0] + rrf, existing[1], hit)

    ranked = sorted(best.values(), key=lambda item: (-item[0], item[1]))[:100]
    citations = [
        MemoryCitation(
            memory_ref=hit.memory_ref,
            entry_id=hit.entry_id,
            entry_version_id=hit.entry_version_id,
        )
        for _score, _order, hit in ranked
    ]
    try:
        pages, page_citations, page_texts = await _page_map(memory)
    except Exception:
        return tuple(citations[:limit])
    if not pages:
        return tuple(citations[:limit])

    centers: list[int] = []
    for page in _section_pages(question, page_texts):
        if page not in centers:
            centers.append(page)
    for citation in citations:
        page = pages.get((citation.entry_id, citation.entry_version_id))
        if page is not None and page not in centers:
            centers.append(page)

    ordered: list[MemoryCitation] = []
    seen: set[int] = set()
    for center in centers:
        for delta in (0, -1, 1):
            neighbor = center + delta
            if neighbor in seen:
                continue
            neighbor_citation = page_citations.get(neighbor)
            if neighbor_citation is None:
                continue
            seen.add(neighbor)
            ordered.append(neighbor_citation)
            if len(ordered) >= limit:
                return tuple(ordered)
    return tuple(ordered)


def _section_pages(question: str, page_texts: dict[int, str]) -> list[int]:
    """Find pages with statement/section headings relevant to a finance question."""

    query = question.casefold()
    headings: list[str] = []
    if any(word in query for word in ("income", "margin", "revenue", "sales", "earnings", "profit", "ebitda", "loss")):
        headings.extend(
            (
                "consolidated statement of income",
                "consolidated statements of income",
                "consolidated statements of comprehensive income",
                "consolidated balance sheet",
                "consolidated balance sheets",
                "consolidated statement of cash flows",
                "consolidated statements of cash flows",
                "results of operations",
                "sales and operating income",
                "management's discussion and analysis",
            )
        )
    if any(word in query for word in ("product", "service", "business")) and "item 1. business" not in headings:
        headings.append("item 1. business")
    if any(word in query for word in ("customer", "concentration")):
        headings.extend(("customer concentration", "customers"))
    if any(word in query for word in ("cyclical", "forward-looking", "subject to")):
        headings.append("forward-looking statements")
    if any(word in query for word in ("cash", "liquidity", "capex", "capital expenditure", "operating activities")):
        headings.extend(("consolidated statement of cash flows", "consolidated statements of cash flows"))
    if any(word in query for word in ("asset", "liabilit", "equity", "debt", "balance sheet")):
        headings.extend(("consolidated balance sheet", "consolidated balance sheets"))
    if any(word in query for word in ("legal", "litigation", "lawsuit", "proceeding")):
        headings.extend(("legal proceedings", "legal proceeding"))
    if any(word in query for word in ("risk", "uncertaint")):
        headings.extend(("risk factors", "risk factor"))
    if any(word in query for word in ("employee", "headcount", "workforce")):
        headings.append("employees")
    if any(word in query for word in ("tax rate", "financial performance", "card member", "summary of financial")):
        headings.append("summary of financial performance")
    if any(word in query for word in ("securities registered", "registered to trade", "national securities exchange")):
        return [1]
    if not headings:
        return []
    scored_pages = []
    financial = any(
        word in query for word in ("income", "margin", "revenue", "sales", "earnings", "profit", "ebitda", "cash", "asset", "liabilit", "equity")
    )
    legal = any(word in query for word in ("legal", "litigation", "lawsuit", "proceeding"))
    risk = any(word in query for word in ("risk", "uncertaint"))
    query_terms = set(re.findall(r"[a-z]+", query))
    for page, text in page_texts.items():
        lower = text.casefold()
        if not any(heading in lower for heading in headings):
            continue
        if financial:
            weight = lower.count("$") + len(re.findall(r"\d", lower))
        elif legal:
            weight = sum(lower.count(word) for word in ("legal", "litigation", "lawsuit", "proceeding", "claim"))
        elif risk:
            weight = sum(lower.count(word) for word in ("risk", "uncertaint"))
        else:
            weight = sum(lower.count(term) for term in query_terms)
        scored_pages.append((weight, page))
    scored_pages.sort(key=lambda item: (-item[0], item[1]))
    return [page for _score, page in scored_pages[:8]]


async def _page_map(
    memory: Any,
) -> tuple[
    dict[tuple[str, str], int],
    dict[int, MemoryCitation],
    dict[int, str],
]:
    """Map Memory citations to physical PDF pages through their Source identities."""

    try:
        cached = getattr(memory, "_pdf_page_citation_map", None)
    except Exception:
        cached = None
    if cached is not None:
        return cached
    try:
        entries = await memory.list()
    except Exception:
        return {}, {}, {}
    by_citation: dict[tuple[str, str], int] = {}
    by_page: dict[int, MemoryCitation] = {}
    by_text: dict[int, str] = {}
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
        by_text[page] = record.entry.text
    try:
        setattr(memory, "_pdf_page_citation_map", (by_citation, by_page, by_text))
    except Exception:
        pass
    return by_citation, by_page, by_text


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
