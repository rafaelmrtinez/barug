from dataclasses import dataclass

@dataclass(frozen=True)
class ActiveScheduleDTO:
    schedule_id: int
    household_name: str
    week_range: str
    status: str