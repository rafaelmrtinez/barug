from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Tuple, List

from maternal.forms.form_utils import FormUtils
from src.infra.utilities.custom_date_time_util import DateAndTimeUtility


class RepositoryPayloadValidator:
    """Utility to validate and sanitize payloads before repository calls.

    Design notes / assumptions:
    - This validator is conservative: it enforces types and replaces missing
      values with safe defaults so that payloads contain no `None` values.
      (If you prefer None for optional DB NULLs, change the `default` in
      the schema below.)
    - Returns a cleaned payload and a list of friendly error messages.
    - Includes a helper `validate_child_screening_payload` tailored for
      the `insert_child_screening` repository method.
    """

    @staticmethod
    def _parse_date(val: Any) -> Tuple[Any, str | None]:
        if val is None or val == "":
            # default to today's PH date string
            try:
                d = DateAndTimeUtility.parse_date(DateAndTimeUtility.get_current_date())
                return d, None
            except Exception:
                return date.today(), None
        if isinstance(val, date):
            return val, None
        if isinstance(val, datetime):
            return val.date(), None
        if isinstance(val, str):
            parsed = DateAndTimeUtility.parse_date(val)
            if parsed:
                return parsed, None
            return None, f"Invalid date format: {val}. Expected YYYY-MM-DD."
        return None, f"Invalid date value: {val}"

    @staticmethod
    def _parse_decimal(val: Any) -> Tuple[Any, str | None]:
        if val is None or val == "":
            return Decimal('0'), None
        try:
            if isinstance(val, Decimal):
                return val, None
            return Decimal(str(val)), None
        except Exception:
            return None, f"Invalid numeric value: {val}"

    @staticmethod
    def _parse_int(val: Any) -> Tuple[Any, str | None]:
        if val is None or val == "":
            return 0, None
        try:
            return int(val), None
        except Exception:
            return None, f"Invalid integer value: {val}"

    @staticmethod
    def _parse_bool(val: Any) -> Tuple[Any, str | None]:
        if isinstance(val, bool):
            return val, None
        if val in (None, ''):
            return False, None
        if isinstance(val, (int, Decimal)):
            return bool(int(val)), None
        s = str(val).strip().lower()
        if s in ('true', '1', 'yes', 'y'):
            return True, None
        if s in ('false', '0', 'no', 'n'):
            return False, None
        return None, f"Invalid boolean value: {val}"

    @staticmethod
    def _parse_string(val: Any, label: str) -> Tuple[Any, str | None]:
        if val is None:
            # canonical fallback
            return 'N/A', None
        sanitized, err = FormUtils.sanitize_text(str(val), label)
        if err:
            return None, err
        return sanitized, None

    @staticmethod
    def validate_payload(payload: Dict[str, Any], schema: Dict[str, Dict[str, Any]]) -> Tuple[Dict[str, Any], List[str]]:
        """Validate generic payload using the provided schema.

        Schema format:
          { 'field_name': {'type': 'date'|'decimal'|'int'|'bool'|'str', 'required': bool} }

        Returns cleaned_payload (with no None values per this util) and errors list.
        """
        cleaned: Dict[str, Any] = {}
        errors: List[str] = []

        for key, rules in schema.items():
            typ = rules.get('type')
            required = rules.get('required', False)
            raw = payload.get(key)

            if typ == 'date':
                val, err = RepositoryPayloadValidator._parse_date(raw)
            elif typ == 'decimal':
                val, err = RepositoryPayloadValidator._parse_decimal(raw)
            elif typ == 'int':
                val, err = RepositoryPayloadValidator._parse_int(raw)
            elif typ == 'bool':
                val, err = RepositoryPayloadValidator._parse_bool(raw)
            elif typ == 'str':
                val, err = RepositoryPayloadValidator._parse_string(raw, key.capitalize())
            else:
                val, err = raw, None

            if err:
                errors.append(f"{key}: {err}")
                # provide a safe default per type
                if typ == 'date':
                    val = DateAndTimeUtility.parse_date(DateAndTimeUtility.get_current_date()) or date.today()
                elif typ == 'decimal':
                    val = Decimal('0')
                elif typ == 'int':
                    val = 0
                elif typ == 'bool':
                    val = False
                elif typ == 'str':
                    val = 'N/A'

            if required and (val is None or (isinstance(val, str) and val.strip() == '')):
                errors.append(f"{key}: is required and missing.")

            cleaned[key] = val

        return cleaned, errors

    @staticmethod
    def validate_child_screening_payload(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """Validate the payload expected by insert_child_screening.

        This enforces types and returns cleaned payload and friendly errors.
        By design this method will not leave `None` values — it substitutes
        safe defaults where appropriate. If you prefer SQL NULLs, callers
        should translate the defaults to None before calling repository.
        """
        schema = {
            'chr_id': {'type': 'int', 'required': True},
            'assessed_by_id': {'type': 'int', 'required': True},
            'date_assessed': {'type': 'date', 'required': True},
            'anemic_seen': {'type': 'date', 'required': False},
            'anemic_given_iron': {'type': 'date', 'required': False},
            'birth_weight': {'type': 'decimal', 'required': True},
            'is_low_birth_weight': {'type': 'bool', 'required': False},
            'seen_2_6_mos': {'type': 'date', 'required': False},
            'given_2_6_mos': {'type': 'date', 'required': False},
            'tt_status': {'type': 'int', 'required': False},
        }

        cleaned, errors = RepositoryPayloadValidator.validate_payload(payload, schema)

        # Additional domain rules
        # birth_weight should be > 0
        try:
            if cleaned.get('birth_weight') is not None and Decimal(cleaned.get('birth_weight')) <= Decimal('0'):
                errors.append('birth_weight must be greater than zero.')
        except Exception:
            errors.append('birth_weight must be a valid number.')

        # If anemic_given_iron present and earlier than anemic_seen -> error
        a_seen = cleaned.get('anemic_seen')
        a_given = cleaned.get('anemic_given_iron')
        if isinstance(a_seen, date) and isinstance(a_given, date):
            if a_given < a_seen:
                errors.append('anemic_given_iron cannot be before anemic_seen.')

        # If given_2_6_mos present and earlier than seen_2_6_mos -> error
        s_seen = cleaned.get('seen_2_6_mos')
        s_given = cleaned.get('given_2_6_mos')
        if isinstance(s_seen, date) and isinstance(s_given, date):
            if s_given < s_seen:
                errors.append('given_2_6_mos cannot be before seen_2_6_mos.')

        return cleaned, errors
