from typing import List, Optional


class IVitaminService:
    """Contract for Vitamin A application service."""

    def apply_stage(self, child_health_record_id: int, staff_id: int, stage_id: Optional[int] = None, requested_stages: Optional[List[int]] = None) -> bool:  # pragma: no cover - interface
        raise NotImplementedError()
