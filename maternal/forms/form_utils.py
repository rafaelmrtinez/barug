from typing import Optional, Tuple
import re


# Basic emoji detection covering common emoji ranges. Conservative by design.
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)


class FormUtils:
    """Reusable form utilities for sanitization and validation.

    Methods are intentionally conservative and return clear, caller-friendly
    results so they can be used in form `clean()` implementations.
    """

    @staticmethod
    def remove_non_printable(s: str) -> str:
        """Return string with only printable characters."""
        return ''.join(ch for ch in s if ch.isprintable())

    @staticmethod
    def contains_emoji(s: str) -> bool:
        """Detect common emoji characters in the string."""
        return bool(_EMOJI_PATTERN.search(s))

    @staticmethod
    def normalize_na(s: str) -> str:
        """Normalize common variants of 'N/A' to canonical 'N/A'."""
        return 'N/A' if s.lower() in ('n/a', 'na') else s

    @staticmethod
    def sanitize_text(value: str, label: str) -> Tuple[Optional[str], Optional[str]]:
        """Sanitize a free-text field and return (normalized_value, error_message).

        - Trims whitespace
        - Removes non-printable characters
        - Returns an error if input is empty after trimming
        - Returns an error if emoji characters are present
        - Normalizes 'n/a'/'na' variants to 'N/A'

        The caller should add the returned error_message to the form using
        `add_error(field_name, error_message)` when appropriate.
        """
        if value is None:
            return None, None

        normalized = value.strip() if isinstance(value, str) else str(value).strip()
        normalized = FormUtils.remove_non_printable(normalized)

        if not normalized:
            return None, f"{label}: please enter a value or type 'N/A' if not applicable."

        if FormUtils.contains_emoji(normalized):
            return None, f"{label}: please remove emojis — use plain text only (e.g. 'N/A' or a short description)."

        if normalized.lower() in ('n/a', 'na'):
            return 'N/A', None

        return normalized, None
