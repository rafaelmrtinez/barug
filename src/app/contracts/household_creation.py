from abc import ABC, abstractmethod


class IHouseholdCreationService(ABC):

    @abstractmethod
    def execute(self, req: 'CreateHouseholdRequest') -> dict:
        pass