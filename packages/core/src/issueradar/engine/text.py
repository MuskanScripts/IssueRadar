"""Small text helpers shared by the engines."""

from __future__ import annotations

import re
from functools import lru_cache

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_STOPWORDS = frozenset(
    [
        "the",
        "and",
        "to",
        "of",
        "a",
        "in",
        "is",
        "it",
        "this",
        "that",
        "for",
        "on",
        "with",
        "when",
        "not",
        "be",
        "are",
        "as",
        "an",
        "or",
        "if",
        "but",
        "from",
        "by",
        "at",
        "was",
        "have",
        "i",
        "we",
        "you",
        "can",
        "should",
        "does",
        "do",
    ]
)
_FILE_PATH = re.compile(
    r"(?<![\w/])(?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]{1,6}\b|`[\w./-]+\.[A-Za-z0-9]{1,6}`"
)
_ISSUE_REF = re.compile(r"(?<![\w/&])#\d+\b")


def normalise(text: str) -> str:
    return " ".join(text.lower().split())


@lru_cache(maxsize=256)
def _phrase_pattern(phrases: tuple[str, ...]) -> re.Pattern[str]:
    # Longest first, so "i'll take this" wins over "take this" when both match.
    ordered = sorted({p.lower() for p in phrases}, key=len, reverse=True)
    alternatives = "|".join(re.escape(p) for p in ordered)
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)")


def contains_any(text: str, phrases: list[str]) -> str | None:
    """Return the phrase found in ``text`` (case-insensitive, whole words), if any.

    When several match, the one listed first in ``phrases`` is returned.
    """
    if not phrases:
        return None
    lowered = normalise(text)
    found = {m.group(0) for m in _phrase_pattern(tuple(phrases)).finditer(lowered)}
    if not found:
        return None
    return next(p for p in phrases if p.lower() in found)


LANGUAGE_SAMPLE_CHARS = 2000  # enough to judge the language; long logs add nothing


def looks_non_english(
    text: str, *, ascii_ratio: float, min_words: int, stopword_ratio: float
) -> bool:
    text = text[:LANGUAGE_SAMPLE_CHARS]
    letters = [c for c in text if c.isalpha()]
    if len(letters) >= 20:
        share = sum(1 for c in letters if c.isascii()) / len(letters)
        if share < ascii_ratio:
            return True
    words = [w.lower() for w in _WORD.findall(text)]
    if len(words) >= min_words:
        stop = sum(1 for w in words if w in _STOPWORDS)
        if stop / len(words) < stopword_ratio:
            return True
    return False


def file_paths(text: str) -> list[str]:
    found = []
    for match in _FILE_PATH.findall(text):
        path = match.strip("`")
        if not path.startswith(("http", "www.")) and path not in found:
            found.append(path)
    return found


def issue_refs(text: str) -> int:
    return len(set(_ISSUE_REF.findall(text)))


def has_code_block(text: str) -> bool:
    return "```" in text or "\n    " in text
