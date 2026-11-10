"""Phrase matching used by the extractors.

A phrase is a few lower-case words. Words are matched whole and
case-insensitively; a space in the phrase also matches a hyphen in the text
("multi agent" finds "multi-agent"); a word ending in ``*`` matches any
ending ("optimi*" finds optimize, optimised, optimization).
"""

from __future__ import annotations

import re
from functools import lru_cache

from .vocab import NEGATION_WINDOW, NEGATIONS


@lru_cache(maxsize=None)
def phrase_regex(phrase: str) -> re.Pattern:
    words = []
    for word in phrase.split():
        if word.endswith("*"):
            words.append(re.escape(word[:-1]) + r"\w*")
        else:
            words.append(re.escape(word))
    return re.compile(r"(?<![\w$])" + r"[\s-]+".join(words) + r"(?!\w)", re.IGNORECASE)


def normalise_quotes(text: str) -> str:
    return text.replace("’", "'").replace("‘", "'")


def find_phrase(text: str, phrases) -> re.Match | None:
    """First match of any phrase in ``text`` that is not negated."""
    text = normalise_quotes(text)
    best = None
    for phrase in phrases:
        for match in phrase_regex(phrase).finditer(text):
            if not is_negated(text, match.start()):
                if best is None or match.start() < best.start():
                    best = match
                break
    return best


def find_all(text: str, phrases) -> list[re.Match]:
    """Every non-negated match of every phrase, in text order."""
    text = normalise_quotes(text)
    matches = [match for phrase in phrases for match in phrase_regex(phrase).finditer(text)
               if not is_negated(text, match.start())]
    return sorted(matches, key=lambda match: match.start())


def has_phrase(text: str, phrases) -> bool:
    return find_phrase(text, phrases) is not None


def is_negated(text: str, position: int) -> bool:
    """True when a negation stands within NEGATION_WINDOW words before ``position``."""
    before = normalise_quotes(text[:position]).lower()
    clause = re.split(r"[.;:!?]", before)[-1]
    words = re.findall(r"[\w']+", clause)[-NEGATION_WINDOW:]
    window = " ".join(words)
    for negation in NEGATIONS:
        if re.search(rf"(?<![\w']){re.escape(negation)}(?![\w'])", window):
            return True
    return any(word.endswith("n't") for word in words)


def labels_in(text: str, table: dict[str, tuple[str, ...]]) -> list[str]:
    """Vocabulary labels whose phrases occur (not negated) in ``text``."""
    return [label for label, phrases in table.items() if has_phrase(text, phrases)]


def normalise_for_quote(text: str) -> str:
    """Whitespace- and case-normalised form used to check that a quote exists."""
    text = normalise_quotes(text).replace("“", '"').replace("”", '"').replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip().lower()
