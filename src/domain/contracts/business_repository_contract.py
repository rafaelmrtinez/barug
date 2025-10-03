from abc import ABC, abstractmethod

from typing import Optional
from src.app.transfer_objects.dto.business_dto import BusinessListDTO
from src.app.transfer_objects.dto.business_dto import ResidentOwnerDTO

class IBusinessRepository(ABC):

    @abstractmethod
    def fetch_business_list(self) -> list[BusinessListDTO]:
        pass

    @abstractmethod
    def search_business(self, search: str) -> list[BusinessListDTO]:
        pass

    @abstractmethod
    def sort_b_type(self, b_type: int) -> list[BusinessListDTO]:
        pass
    
    @abstractmethod
    def sort_ownership_type(self, ownership_type: int) -> list[BusinessListDTO]:
        pass

    @abstractmethod
    def sort_status(self, status: int) -> list[BusinessListDTO]:
        pass

class IResidentOwnerRepository(ABC):

    @abstractmethod
    def search_owner(
       self,
       search: str,
    ) -> list[ResidentOwnerDTO]:
        pass
    
    @abstractmethod
    def get_owner_details(
        self,
        person_id: int,
    ) -> Optional[ResidentOwnerDTO]:
        pass