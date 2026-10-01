from unittest.mock import patch

import pytest

from app.document_processing.factory import TextExtractorFactory
from app.exceptions import DocumentExtractionError


def test_factory_returns_docling_extractor_for_pdf():
    with patch(
        "app.document_processing.factory.DoclingTextExtractor",
        return_value=object(),
    ) as extractor_class:
        extractor = TextExtractorFactory.create("goals.pdf")

    assert extractor is extractor_class.return_value


def test_factory_returns_docling_extractor_for_docx():
    with patch(
        "app.document_processing.factory.DoclingTextExtractor",
        return_value=object(),
    ) as extractor_class:
        extractor = TextExtractorFactory.create("one-to-one.docx")

    assert extractor is extractor_class.return_value


def test_factory_rejects_unsupported_format():
    with pytest.raises(
        DocumentExtractionError,
        match="Unsupported document format",
    ):
        TextExtractorFactory.create("notes.txt")
