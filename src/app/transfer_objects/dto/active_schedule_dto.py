from dataclasses import dataclass

@dataclass(frozen=True)
class ActiveScheduleDTO:
    household_id: int
    schedule_id: int
    household_name: str
    week_range: str
    status: str