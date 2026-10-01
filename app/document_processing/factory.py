from pathlib import Path

from app.document_processing.docling import DoclingTextExtractor
from app.document_processing.interface import TextExtractor
from app.exceptions import DocumentExtractionError


class TextExtractorFactory:
    """Resolve the extractor for a supported document format."""

    SUPPORTED_EXTENSIONS = {
        ".pdf",
        ".docx",
    }

    @classmethod
    def create(cls, file_name: str) -> TextExtractor:
        extension = Path(file_name).suffix.lower()

        if extension not in cls.SUPPORTED_EXTENSIONS:
            raise DocumentExtractionError(
                f"Unsupported document format: {extension or 'unknown'}"
            )

        return DoclingTextExtractor()
