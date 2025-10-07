from abc import ABC, abstractmethod

class IAntenatalCareService(ABC):

    @abstractmethod
    def execute(self, request):
        pass