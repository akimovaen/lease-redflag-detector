"""Checks that a red flag quote is copied verbatim from the lease text."""

import re

_WHITESPACE = re.compile(r"\s+")


def normalize_whitespace(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def quote_in_text(quote: str, text: str) -> bool:
    """True if the quote occurs in the text, ignoring differences in whitespace.

    Line breaks are not part of the wording: OCR text breaks lines in the middle
    of sentences, and a quote copied from it may join them with spaces.
    """
    quote = normalize_whitespace(quote)
    return bool(quote) and quote in normalize_whitespace(text)
