"""Tiered, in-process content moderation for landlord-authored communications.

Pure and deterministic (no DB, no network, no external API/LLM) so tenant
content never leaves the system and the scan is fully testable. Crude by
design: a curated PT-BR lexicon matched against normalized, word-boundaried
text. Two tiers: SEVERE (slurs / hate / explicit threats) blocks sending;
MILD (common profanity) warns with override.

The lexicons are a curated starter set; expanding them is ongoing policy work,
not a code change. Matching normalizes for common evasion (accents, simple
leetspeak, repeated characters) and matches whole word-tokens for the word
lists (so a flagged token never matches as a substring of a clean word).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Single-word profanity / insults → warn (mild).
_MILD: frozenset[str] = frozenset(
    {
        "merda",
        "porra",
        "caralho",
        "bosta",
        "cacete",
        "cuzao",
        "babaca",
        "otario",
        "imbecil",
        "desgracado",
        "lixo",
    }
)

# Single-word hate slurs → block (severe). Curated starter set.
_SEVERE_WORDS: frozenset[str] = frozenset(
    {
        "viado",
        "bicha",
        "retardado",
    }
)

# Multi-word threat / hate phrases → block (severe). Matched as normalized substrings.
_SEVERE_PHRASES: tuple[str, ...] = (
    "vou te matar",
    "te mato",
    "vou te bater",
    "vou te espancar",
    "vou acabar com voce",
)

_LEET = str.maketrans({"@": "a", "4": "a", "3": "e", "1": "i", "0": "o", "$": "s", "5": "s", "7": "t"})
_WORD = re.compile(r"\w+")
_REPEATS = re.compile(r"(.)\1{2,}")


@dataclass(frozen=True)
class ModerationResult:
    severe: tuple[str, ...]  # matched severe terms/phrases → block
    mild: tuple[str, ...]  # matched mild terms → warn

    @property
    def blocked(self) -> bool:
        return bool(self.severe)

    @property
    def flagged(self) -> bool:
        return bool(self.severe or self.mild)


def _normalize(text: str) -> str:
    """Lowercase, strip accents, undo simple leetspeak, collapse repeated chars."""
    stripped = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    lowered = stripped.lower().translate(_LEET)
    return _REPEATS.sub(r"\1", lowered)


def scan(text: str) -> ModerationResult:
    """Scan ``text`` (caller passes subject + body joined) for flagged content."""
    norm = _normalize(text)
    tokens = set(_WORD.findall(norm))
    mild = tuple(sorted(w for w in _MILD if w in tokens))
    severe_words = {w for w in _SEVERE_WORDS if w in tokens}
    severe_phrases = {p for p in _SEVERE_PHRASES if p in norm}
    severe = tuple(sorted(severe_words | severe_phrases))
    return ModerationResult(severe=severe, mild=mild)
