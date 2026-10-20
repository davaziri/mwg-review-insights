"""Verbatim quote checks.

A model's quote is only kept if it can be found in the review's own text. What we store is the
position of the match, and what the app shows is the review text at that position, so a displayed
quote is always the reviewer's exact words.
"""

import re

_WS = re.compile(r"\s+")
_WRAPPING_QUOTES = "\"'“”‘’«»「」"
MIN_QUOTE_CHARS = 3


def _collapse(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace runs to single spaces, keeping a map back to original positions."""
    out: list[str] = []
    index: list[int] = []
    prev_space = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if prev_space:
                continue
            out.append(" ")
            prev_space = True
        else:
            out.append(ch)
            prev_space = False
        index.append(i)
    return "".join(out), index


def locate_quote(text: str, quote: str | None) -> tuple[int, int] | None:
    """Find quote in text. Returns (start, end) offsets into text, or None if it isn't there.

    Tries an exact match, then one that ignores whitespace differences, then one that also
    ignores letter case. Nothing else (no paraphrase, no fuzzy matching) is accepted.
    """
    if not quote:
        return None
    q = quote.strip().strip(_WRAPPING_QUOTES).strip()
    if len(q) < MIN_QUOTE_CHARS:
        return None

    i = text.find(q)
    if i >= 0:
        return i, i + len(q)

    norm_text, index = _collapse(text)
    norm_q = _WS.sub(" ", q)
    for haystack, needle in ((norm_text, norm_q), (norm_text.lower(), norm_q.lower())):
        # lower() can change length for a few characters; only trust it when it doesn't.
        if len(haystack) != len(norm_text):
            continue
        j = haystack.find(needle)
        if j >= 0:
            return index[j], index[j + len(needle) - 1] + 1
    return None
