"""Phrase matching used by the extractors.

A phrase is a few lower-case words. Words are matched whole and
case-insensitively; a space in the phrase also matches a hyphen in the text
("multi agent" finds "multi-agent"); a word ending in ``*`` matches any
ending ("optimi*" finds optimize, optimised, optimization).

A match is discarded when the text around it shows that the sentence does not
claim the thing for the product: a negation before it, a negation right after
it, or a clause about other products (see NEGATIONS, POST_NEGATIONS and
OTHERS_SUBJECTS in vocab.py).
"""

from __future__ import annotations

import re
from functools import lru_cache

from .vocab import (NEGATION_WINDOW, NEGATIONS, OTHERS_NOUNS, OTHERS_QUANTIFIERS, OTHERS_SUBJECTS, POST_NEGATIONS,
                    RHETORICAL_OPENERS)


@lru_cache(maxsize=None)
def phrase_regex(phrase: str) -> re.Pattern:
    words = []
    for word in phrase.split():
        if word == "~":                      # up to two words in between
            words.append(None)
        elif word.endswith("*"):
            words.append(re.escape(word[:-1]) + r"\w*")
        else:
            words.append(re.escape(word))
    pattern = ""
    for index, word in enumerate(words):
        if word is None:
            pattern += r"(?:[\s-]+[\w'$%.]+){0,2}"
        else:
            pattern += (r"[\s-]+" if index else "") + word
    return re.compile(r"(?<![\w$])" + pattern + r"(?!\w)", re.IGNORECASE)


def normalise_quotes(text: str) -> str:
    return text.replace("’", "'").replace("‘", "'")


def clause_before(text: str, position: int) -> str:
    """The part of the sentence before ``position``, back to the last clause break."""
    return re.split(r"[.;:!?]", normalise_quotes(text[:position]).lower())[-1]


def words_before(text: str, position: int, count: int) -> list[str]:
    return re.findall(r"[\w']+", clause_before(text, position))[-count:]


def preceded_by(text: str, position: int, phrases, window: int) -> bool:
    """True when one of ``phrases`` stands within ``window`` words before ``position``."""
    recent = " ".join(words_before(text, position, window))
    return any(phrase_regex(phrase).search(recent) for phrase in phrases)


_POST_NEGATION = re.compile(r"\s*(?:" + "|".join(re.escape(p).replace(r"\ ", r"\s+") for p in POST_NEGATIONS)
                            + r")(?![\w'])", re.IGNORECASE)


# "other tools", "most SEO tools", "many other AI assistants": somebody else's product
_OTHERS = re.compile(r"(?<![\w'])(?:" + "|".join(OTHERS_QUANTIFIERS) + r")(?:\s+[\w'-]+){0,2}\s+(?:"
                     + "|".join(OTHERS_NOUNS) + r")(?![\w'])", re.IGNORECASE)


def is_negated(text: str, start: int, end: int | None = None) -> bool:
    """True when the phrase at ``start``..``end`` is denied or is about others."""
    text = normalise_quotes(text)
    words = words_before(text, start, NEGATION_WINDOW)
    window = " ".join(words)
    for negation in NEGATIONS:
        if re.search(rf"(?<![\w']){re.escape(negation)}(?![\w'])", window):
            return True
    if any(word.endswith("n't") for word in words):
        return True
    # a clause about somebody else: the subject may start before the phrase or contain it
    # ("Most SEO tools give you dashboards": neither SEO nor dashboards is claimed)
    breaks = [m.end() for m in re.finditer(r"[.;:!?]", text[:start])]
    clause_start = breaks[-1] if breaks else 0
    following = re.search(r"[.;:!?]", text[start:])
    clause = text[clause_start:start + following.start() if following else len(text)]
    offset = start - clause_start
    subjects = [*_OTHERS.finditer(clause), *(m for subject in OTHERS_SUBJECTS
                                             for m in phrase_regex(subject).finditer(clause))]
    if any(subject.start() <= offset for subject in subjects):
        return True
    return end is not None and bool(_POST_NEGATION.match(text[end:]))


def find_all(text: str, phrases) -> list[re.Match]:
    """Every match of every phrase that is not negated, in text order."""
    text = normalise_quotes(text)
    matches = [match for phrase in phrases for match in phrase_regex(phrase).finditer(text)
               if not is_negated(text, match.start(), match.end())]
    return sorted(matches, key=lambda match: match.start())


def find_phrase(text: str, phrases) -> re.Match | None:
    """First match of any phrase in ``text`` that is not negated."""
    matches = find_all(text, phrases)
    return matches[0] if matches else None


def has_phrase(text: str, phrases) -> bool:
    return find_phrase(text, phrases) is not None


def labels_in(text: str, table: dict[str, tuple[str, ...]]) -> list[str]:
    """Vocabulary labels whose phrases occur (not negated) in ``text``."""
    return [label for label, phrases in table.items() if has_phrase(text, phrases)]


def is_rhetorical(text: str) -> bool:
    """A question, or a heading that opens like one ("Why ... fail")."""
    stripped = text.strip()
    first = re.match(r"[A-Za-z']+", stripped)
    return stripped.endswith("?") or bool(first and first.group(0).lower() in RHETORICAL_OPENERS)


def normalise_for_quote(text: str) -> str:
    """Whitespace- and case-normalised form used to check that a quote exists."""
    text = normalise_quotes(text).replace("“", '"').replace("”", '"').replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip().lower()
