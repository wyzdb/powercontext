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

"""PDF boundary and real scoped retrieval regression tests (no benchmark labels)."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject

from powercontext.builtin.artifacts.memory import MemoryEntryInput
from powercontext.builtin.persistence.sqlite import SQLiteConfig
from powercontext.builtin.runtime import (
    BuiltinConfig,
    GetMemoryEntryRequest,
    SubmitSourceObservation,
    open_builtin_runtime,
)
from powercontext.builtin.scope import ScopeDraft
from powercontext.sources import SourceDefinitionRegistry, manifest_for_definition, project_source_for_transport
from powercontext.sources.pdf_pages import (
    PDF_PAGE_SOURCE_DEFINITION,
    PDFDocumentInput,
    PDFPageInput,
    parse_pdf_document,
    search_pdf_pages,
)
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY


def make_pdf(*texts: str, password: str | None = None) -> bytes:
    writer = PdfWriter()
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        })
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = stream
    if password is not None:
        writer.encrypt(password, owner_password="owner-only")  # noqa: S106
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_complete_pages_text_and_whole_file_digest():
    raw = make_pdf("Revenue 1,234 and assets 567.89", "", "Cash flows 800")
    pages = parse_pdf_document(PDFDocumentInput(document_id="company:年度/2025", content=raw))
    assert [page.page_number for page in pages] == [1, 2, 3]
    assert "1,234" in pages[0].text and "567.89" in pages[0].text
    assert pages[1].text == "" and "Cash flows 800" in pages[2].text
    assert {page.document_sha256 for page in pages} == {hashlib.sha256(raw).hexdigest()}


@pytest.mark.parametrize("document_id", ["", " \t\n"])
def test_blank_document_id_rejected(document_id):
    with pytest.raises(ValueError):
        PDFDocumentInput(document_id=document_id, content=make_pdf("text"))


def test_permissions_password_and_truncation():
    assert len(parse_pdf_document(PDFDocumentInput(document_id="a", content=make_pdf("", password="")))) == 1
    for raw in (b"", b"not pdf", make_pdf("one", "two")[:-70], make_pdf("secret", password="secret")):  # noqa: S106
        with pytest.raises(ValueError):
            parse_pdf_document(PDFDocumentInput(document_id="a", content=raw))


async def test_broken_later_page_fails_instead_of_returning_prefix():
    raw = make_pdf("first", "second")
    # Keep the xref and valid first page, but make the later page's content invalid.
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    writer.pages[1][NameObject("/Contents")] = ArrayObject([NameObject("/InvalidStream")])
    output = io.BytesIO()
    writer.write(output)
    with pytest.raises(ValueError):
        parse_pdf_document(PDFDocumentInput(document_id="broken", content=output.getvalue()))


async def test_long_identity_roundtrip_and_revisions():
    registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
    page = PDFPageInput(document_id="任意:/" * 1000, document_sha256="a" * 64, page_number=1, text="Revenue 123")
    source = await registry.resolve(page)
    assert len(source.name) <= 256
    assert await registry.read(source) == page
    assert (await registry.resolve(page)).name == source.name
    for other in (
        page.model_copy(update={"document_id": page.document_id + ":1"}),
        page.model_copy(update={"document_sha256": "b" * 64}),
        page.model_copy(update={"page_number": 2}),
    ):
        assert (await registry.resolve(other)).name != source.name


class PagePipeline:
    async def extract(self, request, /):
        return tuple(
            MemoryEntryInput(
                kind="source-evidence",
                text=source.projection(TEXT_EVIDENCE_PROJECTION_KEY)["content"],
                sources=(source,),
            )
            for source in request.sources
        )


async def test_real_memory_restart_scope_distinct_pages_and_limits(tmp_path: Path):
    config = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'pdf.db'}"))
    registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
    pages = parse_pdf_document(
        PDFDocumentInput(
            document_id="ACME_2025_10K",
            content=make_pdf(
                "Consolidated statements of cash flows depreciation amortization 123 capital expenditures 50",
                "Consolidated income statements operating income 456 net sales 789",
                "Legal proceedings litigation and contingencies pending 12",
                "Geographic segments international operations countries North America Europe Asia",
                "Executive compensation bonus salary stock awards 999",
            ),
        )
    )
    observations = [project_source_for_transport(registry, await registry.resolve(page)) for page in pages]
    async with open_builtin_runtime(config, candidate_pipeline=PagePipeline()) as runtime:
        assert runtime.scopes is not None
        scope = await runtime.scopes.create(ScopeDraft(title="Reports", summary="PDF", idempotency_key="reports"))
        other = await runtime.scopes.create(ScopeDraft(title="Other", summary="Isolated", idempotency_key="other"))
        await runtime.ingestion.register(manifest_for_definition(PDF_PAGE_SOURCE_DEFINITION))
        for observation in [*observations, observations[0]]:
            await runtime.ingestion.submit(SubmitSourceObservation(scope_id=scope.scope_id, observation=observation))
        await runtime.ingestion.submit(SubmitSourceObservation(scope_id=other.scope_id, observation=observations[0]))
        for scope_id in (scope.scope_id, other.scope_id):
            while (await runtime.memory.for_scope(scope_id).flush()).processed:
                pass
    async with open_builtin_runtime(config) as runtime:
        memory = runtime.memory.for_scope(scope.scope_id)
        assert await search_pdf_pages(memory, "cash", limit=0) == ()
        assert await search_pdf_pages(memory, "   ", limit=20) == ()
        citations = await search_pdf_pages(memory, "ACME FY2025 EBITDA less capex", limit=2)
        assert len(citations) == 2
        records = [(await memory.get(GetMemoryEntryRequest(citation=citation))).entry for citation in citations]
        assert any("depreciation" in entry.text for entry in records)
        assert any("operating income" in entry.text for entry in records)
        all_citations = await search_pdf_pages(memory, "income cash legal geographic compensation", limit=20)
        assert len(all_citations) == 5
        ids = [citation.entry_id for citation in all_citations]
        assert len(ids) == len(set(ids))
        isolated = await search_pdf_pages(runtime.memory.for_scope(other.scope_id), "cash flows", limit=20)
        assert len(isolated) == 1
        assert isolated[0].entry_id not in ids
