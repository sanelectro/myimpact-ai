from app.services.document_chunking import DocumentChunkingService


def test_chunking_preserves_heading_breadcrumbs():
    markdown = """# Engineering Expectations

Introductory context.

## Technical Leadership

Leadership context.

### Architecture

Drive architecture decisions across services.
"""

    chunks = DocumentChunkingService().chunk(markdown)

    assert [chunk.heading_path for chunk in chunks] == [
        ["Engineering Expectations"],
        ["Engineering Expectations", "Technical Leadership"],
        [
            "Engineering Expectations",
            "Technical Leadership",
            "Architecture",
        ],
    ]
    assert chunks[0].content == "Introductory context."
    assert chunks[-1].content == "Drive architecture decisions across services."


def test_chunking_allows_multiple_chunks_under_same_heading():
    service = DocumentChunkingService(max_chunk_size=40)
    markdown = """# Architecture

First paragraph with enough text.

Second paragraph with enough text.
"""

    chunks = service.chunk(markdown)

    assert len(chunks) == 2
    assert all(chunk.heading_path == ["Architecture"] for chunk in chunks)
    assert [chunk.content for chunk in chunks] == [
        "First paragraph with enough text.",
        "Second paragraph with enough text.",
    ]


def test_chunking_supports_content_without_headings():
    chunks = DocumentChunkingService().chunk(
        "This document has no heading.\n\nIt still contains useful knowledge."
    )

    assert len(chunks) == 1
    assert chunks[0].heading_path == []
    assert chunks[0].content == (
        "This document has no heading.\n\nIt still contains useful knowledge."
    )


def test_chunking_does_not_include_heading_in_content():
    chunks = DocumentChunkingService().chunk(
        "## Technical Leadership\n\nDrive technical decisions."
    )

    assert chunks[0].heading_path == ["Technical Leadership"]
    assert chunks[0].content == "Drive technical decisions."
    assert "Technical Leadership" not in chunks[0].content
