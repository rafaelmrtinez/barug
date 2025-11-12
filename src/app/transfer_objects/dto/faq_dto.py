from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class FAQDTO:
    id: str
    question: str
    answer: str
    document_id: str
    created_at: str

    @classmethod
    def from_dict(cls, obj: Dict[str, Any]) -> "FAQDTO":
        return cls(
            id=str(obj.get("id") or ""),
            question=str(obj.get("question") or ""),
            answer=str(obj.get("answer") or ""),
            document_id=str(obj.get("document_id") or ""),
            created_at=str(obj.get("created_at") or ""),
        )

    @classmethod
    def list_from_response(cls, resp: Dict[str, Any]) -> List["FAQDTO"]:
        data = resp.get("data") if isinstance(resp, dict) else None
        if not data or not isinstance(data, list):
            return []
        return [cls.from_dict(item) for item in data]
