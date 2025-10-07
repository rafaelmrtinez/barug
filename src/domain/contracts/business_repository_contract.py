from abc import ABC, abstractmethod
from typing import Optional
from typing import Optional
from src.app.transfer_objects.commands.business_cmd import(
    RegisterBusinessProfileCmd
)
from src.app.transfer_objects.dto.business_dto import (
    BusinessListDTO,
    ResidentOwnerDTO,
    NonResidentOwnerDTO
)

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

    @abstractmethod
    def register_business(slf, cmd: RegisterBusinessProfileCmd) -> tuple[int,int]:
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

class INonResidentOwnerRepository(ABC):

    @abstractmethod
    def find_duplicate(self, *, email: Optional[str], mobile: Optional[str]) -> Optional[int]:
        """Return person_id if an owner/person exists with same email/mobile, else None."""
        pass

    @abstractmethod
    def insert_owner_details(self) -> NonResidentOwnerDTO:
        """Call SQL register_owner_only(...) then select and return full DTO."""
        pass