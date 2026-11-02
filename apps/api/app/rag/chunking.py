"""Structure-aware chunking: split on headings/paragraphs, pack to a character budget, overlap by sentences."""

import re
from dataclasses import dataclass

from app.ai.providers.base import estimate_tokens
from app.rag.parsing import ParsedPage
from app.rag.text import sentences


@dataclass
class Chunk:
    ordinal: int
    content: str
    page: int | None
    token_count: int


def _blocks(text: str) -> list[str]:
    text = text.replace("\r\n", "\n")
    raw = re.split(r"\n\s*\n|(?=\n#{1,6}\s)", text)
    return [" ".join(b.split()) for b in raw if b.strip()]


def chunk_pages(pages: list[ParsedPage], chunk_size: int = 800, overlap: int = 120) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page in pages:
        buf: list[str] = []
        size = 0
        heading = ""
        for block in _blocks(page.text):
            if block.startswith("#"):
                heading = block.lstrip("# ").strip()
            units = [block] if len(block) <= chunk_size else sentences(block)
            for unit in units:
                if size + len(unit) > chunk_size and buf:
                    chunks.append(_make(len(chunks), buf, page.page))
                    tail, tail_len = [], 0
                    for s in reversed(buf):
                        if tail_len + len(s) > overlap:
                            break
                        tail.insert(0, s)
                        tail_len += len(s)
                    buf = ([heading] if heading and heading not in tail else []) + tail
                    size = sum(len(s) for s in buf)
                buf.append(unit)
                size += len(unit)
        if buf:
            chunks.append(_make(len(chunks), buf, page.page))
    return [c for c in chunks if c.content.strip()]


def _make(ordinal: int, parts: list[str], page: int | None) -> Chunk:
    content = "\n\n".join(parts).strip()
    return Chunk(ordinal=ordinal, content=content, page=page, token_count=estimate_tokens(content))
