from abc import ABC, abstractmethod

class IAntenatalCareService(ABC):

    @abstractmethod
    def execute(self, init_data, lab_results: dict, tt_vaccines: dict):
        pass