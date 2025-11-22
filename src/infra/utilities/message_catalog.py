from typing import Dict


# Simple message catalog for domain errors. This is intentionally lightweight
# and returns English messages by default. It provides a single place to
# centralize user-facing strings and makes it straightforward to replace
# with Django's gettext or another i18n system later.


class MessageCatalog:
    """Class-based message catalog.

    Use `MessageCatalog.translate(key, **kwargs)` to obtain a formatted
    user-facing string. This keeps the API explicit and makes it easy to
    swap implementations or add per-request localization later.
    """

    _MESSAGES: Dict[str, str] = {
        "no_input": "No Vitamin A stage provided",
        "all_recorded": "All Vitamin A stages are already recorded; no further insertions allowed",
        "invalid_stage_id": "Invalid stage id",
        "invalid_requested_stages": "Invalid requested vitamin stages",
        "invalid_stage_value": "Vitamin stage must be 1, 2, or 3",
        "already_exists": "Vitamin A stage {stage} already exists and cannot be re-added",
        "stage2_requires_1": "Stage 2 requires Stage 1 to be present or selected",
        "stage3_requires_1_2": "Stage 3 requires stages 1 and 2 to be present or selected",
        "max_three": "Cannot add more than three Vitamin A stages",
    }

    @classmethod
    def translate(cls, key: str, **kwargs) -> str:
        tpl = cls._MESSAGES.get(key, key)
        try:
            return tpl.format(**kwargs)
        except Exception:
            return tpl

