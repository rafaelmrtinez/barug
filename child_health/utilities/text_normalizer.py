"""Lightweight text normalization helpers used across child_health.

Functions here intentionally minimal and dependency-free so they can be
called from views, services or repository layers without importing heavy
libraries.

Primary behavior:
- lower(text)
- replace underscores with spaces
- collapse repeated whitespace

Example:
    >>> normalize_text('Some_TEXT__Here ')
    'some text here'

Returned value is always a str (empty string for None inputs).
"""
from __future__ import annotations

from typing import Any
import unicodedata


class TextNormalizer:
    """Class-based text normalizer exposing a static normalize method.

    Using a class with a static method makes the API explicit and
    easier to mock or extend in tests.
    """

    @staticmethod
    def normalize_text(value: Any) -> str:
        """Normalize input text to a consistent searchable form.

        Steps performed (in order):
        1. If value is None -> return empty string.
        2. Cast to str.
        3. Unicode normalize (NFKC) to reduce equivalent codepoints.
        4. Replace underscores '_' with spaces ' '.
        5. Convert to lower-case.
        6. Collapse repeated whitespace to a single space and strip edges.

        Args:
            value: Any object; the function calls str(value) when not None.

        Returns:
            Normalized str.
        """
        if value is None:
            return ""

        # basic string coercion
        s = str(value)

        # Unicode normal form to avoid visually-equivalent mismatches
        try:
            s = unicodedata.normalize("NFKC", s)
        except Exception:
            # keep original if normalization fails for some reason
            pass

        # replace underscores with spaces (user request)
        if "_" in s:
            s = s.replace("_", " ")

        # lower-case
        s = s.lower()

        # collapse whitespace (tabs/newlines/multiple spaces) to a single space
        parts = s.split()
        return " ".join(parts)


# module-level convenience wrapper for backwards compatibility
def normalize_text(value: Any) -> str:
    return TextNormalizer.normalize_text(value)
