"""Secure document parsing for PDF, DOCX and TXT/Markdown uploads."""

import io
import re
import zipfile
from dataclasses import dataclass

from app.core.errors import AppError

ALLOWED = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


class UnsupportedFile(AppError):
    status_code = 415
    code = "unsupported_file"


@dataclass
class ParsedPage:
    page: int | None
    text: str


def sniff(filename: str, data: bytes) -> str:
    """Validate extension AND magic bytes; never trust the client's Content-Type."""
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in ALLOWED:
        raise UnsupportedFile(f"File type '{ext or 'unknown'}' is not allowed. Allowed: PDF, DOCX, TXT, MD")
    if ext == ".pdf" and not data.startswith(b"%PDF-"):
        raise UnsupportedFile("File content is not a valid PDF")
    if ext == ".docx":
        if not data.startswith(b"PK"):
            raise UnsupportedFile("File content is not a valid DOCX")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if "word/document.xml" not in z.namelist():
                    raise UnsupportedFile("DOCX archive is missing word/document.xml")
                if sum(i.file_size for i in z.infolist()) > 200 * 1024 * 1024:
                    raise UnsupportedFile("DOCX expands beyond the allowed size")
        except zipfile.BadZipFile:
            raise UnsupportedFile("DOCX archive is corrupt")
    if ext in (".txt", ".md"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise UnsupportedFile("Text files must be UTF-8 encoded")
    return ALLOWED[ext]


def safe_filename(name: str) -> str:
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    return name[:200] or "upload"


def parse(content_type: str, data: bytes) -> list[ParsedPage]:
    if content_type == "application/pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return [ParsedPage(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
    if content_type.endswith("wordprocessingml.document"):
        import docx

        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs if p.text.strip()]
        for table in d.tables:
            for row in table.rows:
                parts.append(" | ".join(c.text.strip() for c in row.cells))
        return [ParsedPage(None, "\n\n".join(parts))]
    return [ParsedPage(None, data.decode("utf-8"))]
