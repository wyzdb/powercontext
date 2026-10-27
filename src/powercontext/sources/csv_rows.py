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

"""CSV row Sources and their canonical text-evidence projection."""

from __future__ import annotations

import csv
import io
import json
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import (
    TEXT_EVIDENCE_PROJECTION_KEY,
    AdapterSourceDefinition,
    Source,
    SourceMaterialization,
    TextEvidence,
)

CSV_ROW_SOURCE_NAME = "csv-row"
CSV_ROW_SOURCE_VERSION = "1"


class CSVDocumentInput(BaseModel):
    """One complete, offline CSV document to index by primary key."""

    model_config = ConfigDict(frozen=True)

    document_id: str
    primary_key: str
    content: bytes


class CSVRowInput(BaseModel):
    """One validated CSV row, preserving its original columns and values."""

    model_config = ConfigDict(frozen=True)

    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]


class CSVRowSource(Source):
    """Captured evidence for exactly one CSV row."""

    source_id: str
    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]


def csv_row_source_id(document_id: str, primary_key_value: str, /) -> str:
    """Build the stable, delimiter-safe identity for one CSV row."""

    _validate_document_id(document_id)
    if not isinstance(primary_key_value, str) or not primary_key_value.strip():
        raise ValueError("primary_key_value must be a non-empty string")
    source_id = f"csv:{quote(document_id, safe='')}:{quote(primary_key_value, safe='')}"
    if len(source_id) > MAX_SOURCE_ID_LENGTH:
        raise ValueError(f"csv-row source_id must not exceed {MAX_SOURCE_ID_LENGTH} characters")
    return source_id


def parse_csv_document(document: CSVDocumentInput, /) -> tuple[CSVRowInput, ...]:
    """Parse and validate one offline CSV document without returning partial rows."""

    _validate_document_id(document.document_id)
    if not isinstance(document.primary_key, str) or not document.primary_key:
        raise ValueError("primary_key must be a non-empty string")
    if not isinstance(document.content, bytes):
        raise ValueError("CSV content must be bytes")

    try:
        text = document.content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("CSV content must be valid UTF-8") from error

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader)
    except StopIteration as error:
        raise ValueError("CSV document must contain a header") from error
    except csv.Error as error:
        raise ValueError(f"malformed CSV: {error}") from error

    if not header:
        raise ValueError("CSV header must not be empty")
    seen_columns: set[str] = set()
    for column in header:
        if not column or not column.strip():
            raise ValueError("CSV header fields must be non-empty and non-blank")
        if column in seen_columns:
            raise ValueError("CSV header fields must be unique")
        seen_columns.add(column)

    if document.primary_key not in header:
        raise ValueError("primary_key must exactly match a CSV header field")
    key_index = header.index(document.primary_key)

    rows: list[CSVRowInput] = []
    seen_keys: set[str] = set()
    try:
        for record in reader:
            if not record:
                continue
            if len(record) != len(header):
                raise ValueError("CSV record width must match the header width")
            key = record[key_index]
            if not key or not key.strip():
                raise ValueError("CSV primary key values must be non-empty and non-blank")
            if key in seen_keys:
                raise ValueError("CSV primary key values must be unique within a document")
            seen_keys.add(key)
            rows.append(
                CSVRowInput(
                    document_id=document.document_id,
                    primary_key=document.primary_key,
                    primary_key_value=key,
                    columns=tuple(header),
                    values=tuple(record),
                )
            )
    except csv.Error as error:
        raise ValueError(f"malformed CSV: {error}") from error

    return tuple(rows)


def _validate_document_id(document_id: str) -> None:
    if (
        not isinstance(document_id, str)
        or not document_id.strip()
        or document_id != document_id.strip()
    ):
        raise ValueError("document_id must be a non-empty string without surrounding whitespace")


class CSVRowSourceAdapter:
    """Resolve and read the captured CSV row Source."""

    input_class = CSVRowInput
    name = CSV_ROW_SOURCE_NAME
    source_class = CSVRowSource

    async def resolve(self, value: CSVRowInput, /) -> CSVRowSource:
        source_id = csv_row_source_id(value.document_id, value.primary_key_value)
        return CSVRowSource(
            name=source_id,
            source_id=source_id,
            materialization=SourceMaterialization.CAPTURED,
            document_id=value.document_id,
            primary_key=value.primary_key,
            primary_key_value=value.primary_key_value,
            columns=value.columns,
            values=value.values,
        )

    async def read(self, source: CSVRowSource, /) -> CSVRowInput:
        return CSVRowInput(
            document_id=source.document_id,
            primary_key=source.primary_key,
            primary_key_value=source.primary_key_value,
            columns=tuple(source.columns),
            values=tuple(source.values),
        )


class CSVRowTextEvidenceProjection:
    """Expose a CSV row as the standard text evidence consumed by Memory."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = CSVRowSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: CSVRowSource, /) -> TextEvidence:
        row = dict(zip(source.columns, source.values, strict=True))
        return TextEvidence(
            source_type=CSV_ROW_SOURCE_NAME,
            source_id=source.source_id,
            content=json.dumps(row, ensure_ascii=False, separators=(",", ":")),
            metadata={
                "document_id": source.document_id,
                "primary_key": source.primary_key,
                "primary_key_value": source.primary_key_value,
                "columns": list(source.columns),
                "row": row,
            },
        )


CSV_ROW_SOURCE_ADAPTER = CSVRowSourceAdapter()
CSV_ROW_SOURCE_DEFINITION = AdapterSourceDefinition(
    CSV_ROW_SOURCE_ADAPTER,
    version=CSV_ROW_SOURCE_VERSION,
    projections=(CSVRowTextEvidenceProjection(),),
)

__all__ = [
    "CSV_ROW_SOURCE_ADAPTER",
    "CSV_ROW_SOURCE_DEFINITION",
    "CSV_ROW_SOURCE_NAME",
    "CSV_ROW_SOURCE_VERSION",
    "CSVDocumentInput",
    "CSVRowInput",
    "CSVRowSource",
    "CSVRowSourceAdapter",
    "CSVRowTextEvidenceProjection",
    "csv_row_source_id",
    "parse_csv_document",
]
