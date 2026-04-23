from dataclasses import asdict, is_dataclass
from typing import Any
from psycopg2.extras import Json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import json

from src.infra.exceptions.json_conversion_exception import JSONConversionException

class JSONConverterUtility:
    
    @staticmethod
    def pydantic_object_to_json(list_of_obj: list[object]) -> str:
        """CONVERTS A LIST OF PYDANTIC OBJECTS TO JSON STRING"""
        return json.dumps([obj.model_dump() for obj in list_of_obj], default=str)
    
    @staticmethod
    def to_json_object(value) -> Json:
        return Json(value)
    
    @staticmethod
    def _to_json_array(value, field_name) -> Json:
        if value is None or value == '':
            return Json([])
        if is_dataclass(value):
            value = asdict(value)
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception:
                raise JSONConversionException(f"{field_name} must be valid JSON text", 400)
        if isinstance(value, list):
            return Json(value)
        if isinstance(value, dict):
            raise JSONConversionException(f"{field_name} must be a JSON array", 400)
        raise JSONConversionException(f"Unsupported type for {field_name}", 400)

    @staticmethod
    def __default(o) -> Any | float | Any | dict[str, Any] | str:
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, Enum):
            return o.value
        if is_dataclass(o):
            return asdict(o)
        # Fallback:
        return str(o)

    @staticmethod
    def deep_conversion(data) -> str:
        """It is suggested to use this conversion method if you are working with complex deeply nested objects.
        Otherwise, use the _to_json_array method for simple lists.

        Args:
            data (_type_): json serializable data

        Returns:
            _type_: json string
        """
        payload = asdict(data) if is_dataclass(data) else data
        return json.dumps(payload, indent=4, ensure_ascii=False, default=JSONConverterUtility.__default)