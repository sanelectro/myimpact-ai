from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.document import DocumentScopeType, DocumentType
from app.models.document_chunk import DocumentChunk


def build_chunk(**overrides):
    values = {
        "id": "chunk-1",
        "document_id": "document-1",
        "chunk_index": 0,
        "content": "Drive architecture decisions.",
        "heading_path": [
            "Engineering Expectations",
            "Technical Leadership",
            "Architecture",
        ],
        "document_type": DocumentType.ROLE,
        "scope_type": DocumentScopeType.EMPLOYEE,
        "scope_id": "employee-1",
        "metadata": {"source_page": 3},
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    values.update(overrides)
    return DocumentChunk(**values)


def test_document_chunk_preserves_heading_path_as_canonical_structure():
    chunk = build_chunk()

    assert chunk.heading_path == [
        "Engineering Expectations",
        "Technical Leadership",
        "Architecture",
    ]


def test_document_chunk_allows_content_without_heading():
    chunk = build_chunk(heading_path=[])

    assert chunk.heading_path == []


def test_document_chunk_derivable_heading_values_are_not_persisted_fields():
    chunk = build_chunk()

    assert chunk.heading_path[-1] == "Architecture"
    assert len(chunk.heading_path) == 3
    assert " > ".join(chunk.heading_path) == (
        "Engineering Expectations > Technical Leadership > Architecture"
    )
    assert not hasattr(chunk, "heading")
    assert not hasattr(chunk, "heading_level")
    assert not hasattr(chunk, "heading_path_text")


def test_document_chunk_rejects_negative_chunk_index():
    with pytest.raises(ValidationError):
        build_chunk(chunk_index=-1)


def test_document_chunk_rejects_empty_content():
    with pytest.raises(ValidationError):
        build_chunk(content="")