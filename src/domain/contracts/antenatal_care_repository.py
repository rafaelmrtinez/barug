from abc import ABC, abstractmethod


class IAntenatalCareRepository(ABC):

    @abstractmethod
    def insert_anc_visit(self, request):
        pass
