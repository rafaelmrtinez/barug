import re
from decimal import Decimal, InvalidOperation
from typing import Tuple, Any


class ValidationUtils:
    """Infrastructure-level parsing and validation helpers.

    The emoji detection below uses a comprehensive regex covering common
    Unicode emoji ranges. This is more reliable than checking ordinal
    values and avoids false negatives for many pictographs.
    """

    # emoji unicode ranges (covers emoticons, symbols & pictographs,
    # transport & map symbols, flags, dingbats, etc.)
    _EMOJI_RE = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E6-\U0001F1FF"  # flags
        "\u2600-\u26FF"          # misc symbols
        "\u2700-\u27BF"          # dingbats
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA70-\U0001FAFF"  # symbols and pictographs extended-A
        "]+",
        flags=re.UNICODE,
    )

    @staticmethod
    def parse_decimal(value: Any) -> Decimal:
        try:
            if isinstance(value, Decimal):
                return value
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError("Invalid number format")

    @classmethod
    def contains_emoji(cls, text: str) -> bool:
        """Return True if `text` contains any emoji characters.

        Uses a regex over known emoji ranges; returns False for non-strings.
        """
        if not isinstance(text, str):
            return False
        return bool(cls._EMOJI_RE.search(text))

    @classmethod
    def sanitize_no_emoji(cls, text: str) -> str:
        """Trim whitespace and fail if emoji characters are present.

        Raising `ValueError` preserves previous behaviour while using the
        improved emoji detector.
        """
        if not isinstance(text, str):
            return text
        if cls.contains_emoji(text):
            raise ValueError("Emoji characters are not allowed")
        # Trim and normalize whitespace
        return " ".join(text.strip().split())
