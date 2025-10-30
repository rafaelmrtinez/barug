from dataclasses import dataclass


@dataclass(frozen=True)
class RescheduleCommand:
    p_schedule_id: int
    p_new_week_id: int
    p_reason: str
    p_resched_by_id: int