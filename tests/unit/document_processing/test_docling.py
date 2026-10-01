from unittest.mock import Mock, patch

import pytest

from app.document_processing.docling import DoclingTextExtractor
from app.exceptions import DocumentExtractionError


def test_extract_pdf_to_markdown():
    extractor = DoclingTextExtractor()

    mock_result = Mock()
    mock_result.document.export_to_markdown.return_value = (
        "# Lead Engineer Expectations\n\n"
        "Technical leadership expectations."
    )

    with patch.object(extractor.converter, "convert", return_value=mock_result):
        result = extractor.extract(b"%PDF-test-content", "expectations.pdf")

    assert result == (
        "# Lead Engineer Expectations\n\n"
        "Technical leadership expectations."
    )


def test_extract_docx_to_markdown():
    extractor = DoclingTextExtractor()

    mock_result = Mock()
    mock_result.document.export_to_markdown.return_value = (
        "# Goals\n\nImprove architecture leadership."
    )

    with patch.object(extractor.converter, "convert", return_value=mock_result):
        result = extractor.extract(
            b"docx-test-content",
            "goals.docx",
        )

    assert result == "# Goals\n\nImprove architecture leadership."


def test_extract_raises_when_no_content():
    extractor = DoclingTextExtractor()

    mock_result = Mock()
    mock_result.document.export_to_markdown.return_value = ""

    with patch.object(extractor.converter, "convert", return_value=mock_result):
        with pytest.raises(DocumentExtractionError):
            extractor.extract(b"empty-content", "empty.pdf")