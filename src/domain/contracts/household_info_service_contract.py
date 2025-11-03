from abc import ABC, abstractmethod

# from supabase_auth import Any

class IHouseholdInfoService(ABC):
    Any = 'testing ni raph'
    @abstractmethod
    def execute(self, household_id: int) -> dict[str, dict[str, Any] | list]:
        pass