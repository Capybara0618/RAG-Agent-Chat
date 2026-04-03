from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


@dataclass
class SourceSection:
    heading: str
    location: str
    content: str
    metadata: dict[str, str]


class DocumentParser:
    def detect_source_type(self, name: str, remote_url: str | None = None) -> str:
        if remote_url:
            return "html"
        suffix = Path(name).suffix.lower()
        if suffix == ".pdf":
            return "pdf"
        if suffix == ".docx":
            return "docx"
        if suffix in {".md", ".markdown"}:
            return "markdown"
        if suffix == ".csv":
            return "faq_csv"
        return "text"

    def parse_bytes(self, *, name: str, data: bytes, remote_url: str | None = None) -> tuple[str, list[SourceSection]]:
        source_type = self.detect_source_type(name, remote_url)
        if remote_url:
            text = self._fetch_remote_text(remote_url)
            return "html", self._split_markdown_like(remote_url, text)
        if source_type == "pdf":
            return source_type, self._parse_pdf(data)
        if source_type == "docx":
            return source_type, self._parse_docx(data)
        if source_type == "faq_csv":
            return source_type, self._parse_faq_csv(data)

        text = data.decode("utf-8", errors="ignore")
        return source_type, self._split_markdown_like(name, text)

    def _fetch_remote_text(self, url: str) -> str:
        request = Request(url, headers={"User-Agent": "KnowledgeOpsCopilot/0.1"})
        with urlopen(request, timeout=8) as response:
            html = response.read().decode("utf-8", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.text.strip() if soup.title and soup.title.text else url
        blocks = [title]
        for tag in soup.find_all(["h1", "h2", "h3", "p", "li"]):
            text = tag.get_text(" ", strip=True)
            if text:
                blocks.append(text)
        return "\n\n".join(blocks)

    def _parse_pdf(self, data: bytes) -> list[SourceSection]:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("pypdf is required to parse PDF files.") from exc

        reader = PdfReader(io.BytesIO(data))
        sections: list[SourceSection] = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                sections.extend(self._split_markdown_like(f"Page {index}", text, location_prefix=f"page {index}"))
        return sections

    def _parse_docx(self, data: bytes) -> list[SourceSection]:
        try:
            from docx import Document as DocxDocument
        except ImportError as exc:
            raise RuntimeError("python-docx is required to parse DOCX files.") from exc

        doc = DocxDocument(io.BytesIO(data))
        lines = [paragraph.text.strip() for paragraph in doc.paragraphs if paragraph.text.strip()]
        return self._split_markdown_like("DOCX", "\n\n".join(lines))

    def _parse_faq_csv(self, data: bytes) -> list[SourceSection]:
        text_stream = io.StringIO(data.decode("utf-8", errors="ignore"))
        reader = csv.DictReader(text_stream)
        sections: list[SourceSection] = []
        for index, row in enumerate(reader, start=1):
            question = row.get("question", "").strip()
            answer = row.get("answer", "").strip()
            category = row.get("category", "").strip()
            if not question and not answer:
                continue
            sections.append(
                SourceSection(
                    heading=category or "FAQ",
                    location=f"row {index}",
                    content=f"Question: {question}\nAnswer: {answer}",
                    metadata={"category": category},
                )
            )
        return sections

    def _split_markdown_like(self, title: str, text: str, location_prefix: str = "section") -> list[SourceSection]:
        lines = text.splitlines()
        heading = title
        buffer: list[str] = []
        sections: list[SourceSection] = []
        section_index = 1

        def flush() -> None:
            nonlocal buffer, section_index
            content = "\n".join(buffer).strip()
            if content:
                sections.append(
                    SourceSection(
                        heading=heading,
                        location=f"{location_prefix} {section_index}",
                        content=content,
                        metadata={},
                    )
                )
                section_index += 1
            buffer = []

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                if buffer:
                    buffer.append("")
                continue
            if line.startswith("#"):
                flush()
                heading = line.lstrip("#").strip() or title
                continue
            buffer.append(line)
        flush()

        if not sections:
            normalized = re.sub(r"\s+", " ", text).strip()
            if normalized:
                sections.append(SourceSection(heading=title, location=f"{location_prefix} 1", content=normalized, metadata={}))
        return sections