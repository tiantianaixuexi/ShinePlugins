"""Text helpers shared by the novel services."""

from __future__ import annotations

import re

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")


def count_words(text: str) -> int:
    """Count "words" the way a Chinese novelist does.

    Each CJK character counts as one, and each Latin/number run counts as one
    word. Whitespace and punctuation are ignored.
    """
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    latin = len(_LATIN_WORD_RE.findall(_CJK_RE.sub(" ", text)))
    return cjk + latin


def split_paragraphs(text: str) -> list[str]:
    """Split manuscript text into paragraphs, dropping empty ones."""
    if not text:
        return []
    return [block.strip() for block in _PARAGRAPH_SPLIT_RE.split(text) if block.strip()]


def excerpt(text: str, limit: int = 120) -> str:
    """Single-line preview used in lists."""
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else f"{collapsed[:limit]}…"


def reading_minutes(words: int, cpm: int = 400) -> int:
    """Rough reading time in minutes for a status line."""
    if words <= 0:
        return 0
    return max(1, round(words / cpm))
