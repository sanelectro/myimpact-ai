from abc import ABC, abstractmethod


class TextExtractor(ABC):
    """Contract for extracting normalized Markdown from documents."""

    @abstractmethod
    def extract(
        self,
        content: bytes,
        file_name: str,
    ) -> str:
        """Extract normalized Markdown from document bytes."""
        raise NotImplementedError
