from io import BytesIO

from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.document_converter import DocumentConverter
from docling.exceptions import ConversionError

from app.document_processing.interface import TextExtractor
from app.exceptions import DocumentExtractionError


class DoclingTextExtractor(TextExtractor):
    """Extract normalized Markdown using Docling."""

    SUPPORTED_FORMATS = {
        InputFormat.PDF,
        InputFormat.DOCX,
    }

    def __init__(self) -> None:
        self.converter = DocumentConverter(
            allowed_formats=list(self.SUPPORTED_FORMATS),
        )

    def extract(
        self,
        content: bytes,
        file_name: str,
    ) -> str:
        source = DocumentStream(
            name=file_name,
            stream=BytesIO(content),
        )

        try:
            result = self.converter.convert(source)
            markdown = result.document.export_to_markdown().strip()
        except (
            ConversionError,
            OSError,
            ValueError,
        ) as exc:
            raise DocumentExtractionError(
                f"Failed to extract text from document: {file_name}"
            ) from exc

        if not markdown:
            raise DocumentExtractionError(
                f"No extractable content found in document: {file_name}"
            )

        return markdown
