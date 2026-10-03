import re
from dataclasses import dataclass


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class DocumentChunkContent:
    """Chunk content produced from normalized document Markdown."""

    content: str
    heading_path: list[str]


@dataclass
class _Section:
    heading_path: list[str]
    lines: list[str]


class DocumentChunkingService:
    """Convert normalized Markdown into ordered, heading-aware chunks."""

    def __init__(self, max_chunk_size: int = 2000) -> None:
        if max_chunk_size < 1:
            raise ValueError("max_chunk_size must be greater than zero.")
        self.max_chunk_size = max_chunk_size

    def chunk(self, markdown: str) -> list[DocumentChunkContent]:
        if not markdown.strip():
            return []

        sections = self._parse_sections(markdown)
        chunks: list[DocumentChunkContent] = []

        for section in sections:
            content = self._normalize_content(section.lines)
            if not content:
                continue

            for piece in self._split_content(content):
                chunks.append(
                    DocumentChunkContent(
                        content=piece,
                        heading_path=list(section.heading_path),
                    )
                )

        return chunks

    def _parse_sections(self, markdown: str) -> list[_Section]:
        sections: list[_Section] = []
        heading_stack: list[tuple[int, str]] = []
        current_lines: list[str] = []
        current_path: list[str] = []

        for line in markdown.splitlines():
            match = _HEADING_RE.match(line)
            if match:
                if current_lines:
                    sections.append(
                        _Section(
                            heading_path=current_path,
                            lines=current_lines,
                        )
                    )
                    current_lines = []

                level = len(match.group(1))
                title = self._normalize_heading(match.group(2))

                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()

                heading_stack.append((level, title))
                current_path = [heading for _, heading in heading_stack]
                continue

            current_lines.append(line)

        if current_lines:
            sections.append(
                _Section(
                    heading_path=current_path,
                    lines=current_lines,
                )
            )

        return sections

    @staticmethod
    def _normalize_heading(heading: str) -> str:
        return re.sub(r"\s+#+\s*$", "", heading).strip()

    @staticmethod
    def _normalize_content(lines: list[str]) -> str:
        text = "\n".join(lines).strip()
        return re.sub(r"\n{3,}", "\n\n", text)

    def _split_content(self, content: str) -> list[str]:
        if len(content) <= self.max_chunk_size:
            return [content]

        paragraphs = [
            paragraph.strip()
            for paragraph in re.split(r"\n\s*\n", content)
            if paragraph.strip()
        ]

        chunks: list[str] = []
        current = ""

        for paragraph in paragraphs:
            if len(paragraph) > self.max_chunk_size:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.extend(self._split_long_text(paragraph))
                continue

            candidate = paragraph if not current else f"{current}\n\n{paragraph}"
            if len(candidate) <= self.max_chunk_size:
                current = candidate
            else:
                chunks.append(current)
                current = paragraph

        if current:
            chunks.append(current)

        return chunks

    def _split_long_text(self, text: str) -> list[str]:
        pieces: list[str] = []
        remaining = text.strip()

        while len(remaining) > self.max_chunk_size:
            boundary = remaining.rfind(" ", 0, self.max_chunk_size + 1)
            if boundary <= 0:
                boundary = self.max_chunk_size

            pieces.append(remaining[:boundary].strip())
            remaining = remaining[boundary:].strip()

        if remaining:
            pieces.append(remaining)

        return pieces
