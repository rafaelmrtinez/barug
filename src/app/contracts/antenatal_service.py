from abc import ABC, abstractmethod

class IAntenatalCareService(ABC):

    @abstractmethod
    def execute(self, init_data, raw_lab_results, raw_tt_vaccines):
        pass