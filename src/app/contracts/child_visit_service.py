from typing import Any, Dict


class IChildVisitService:
    def process_and_insert(self, chr_id: int, staff_id: int, staff_role: str, payload: Dict[str, Any]) -> Any:  # pragma: no cover - interface
        raise NotImplementedError()
