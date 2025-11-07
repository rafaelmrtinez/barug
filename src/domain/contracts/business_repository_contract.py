from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional, Dict, Any
from src.app.transfer_objects.commands.business_cmd import(
    RegisterBusinessProfileCmd,
    CreateRenewalRequestCmd,
)
from src.app.transfer_objects.dto.business_dto import (
    BusinessListDTO,
    ResidentOwnerDTO,
    NonResidentOwnerDTO,
    BusinessInfoDTO,
    RenewalListDTO,
    RenewalQuoteLineDTO,
)

class IBusinessRepository(ABC):

    @abstractmethod
    def fetch_business_list(self) -> list[BusinessListDTO]:
        pass

    @abstractmethod
    def search_business(self, search: str) -> list[BusinessListDTO]:
        pass

    @abstractmethod
    def sort_b_category(self, b_type: int) -> list[BusinessListDTO]:
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
    
    @abstractmethod
    def fetch_business_pins(
        self,
        *,
        search: Optional[str] = None,
        b_category: Optional[int] = None,
        ownership_type: Optional[int] = None,
        status: Optional[int] = None,
    ) -> list[Dict[str, Any]]:
        pass

    @abstractmethod
    def find_duplicate_business(
        self,
        *,
        owner_person_id: int,
        business_name: str,
        city: str,
        barangay: str,
        street: str,
        purok_sitio_id: Optional[int],
        b_category_id: Optional[int],
    ) -> Optional[int]:
        pass

class IResidentOwnerRepository(ABC):

    @abstractmethod
    def search_owner(
       self,
       search: str,
       * ,
       only_nonresident: bool = False
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

class IBusinessRenewalRepository(ABC):
    @abstractmethod
    def fetch_business_renewal_list(self) -> list[RenewalListDTO]:
        pass

    @abstractmethod
    def search_business_renewal(self, search: str) -> list[RenewalListDTO]:
        pass

    @abstractmethod
    def sort_clearance_sate(self, b_type: int) -> list[RenewalListDTO]:
        pass

class IBusinessRenewalQuoteRepository(ABC):
    @abstractmethod
    def fetch_quote_auto(self, business_id: int, year: int) -> list[RenewalQuoteLineDTO]:
        """Calls public.get_bc_renewal_quote_auto(..) and maps rows to DTOs."""
        pass

    @abstractmethod
    def fetch_grand_total_auto(self, business_id: int, year: int) -> Decimal:
        """Calls public.get_bc_renewal_grand_total_auto(..)."""
        pass

    @abstractmethod
    def fetch_paid_history(self, business_id: int) -> list[Dict[str, Any]]:
        """Paid rows (annual) for reference; uses business_clearance_status_record."""
        pass

class IBusinessRenewalRequestRepository(ABC):
    @abstractmethod
    def request_renewal(self, cmd: CreateRenewalRequestCmd) -> int:
        """Calls public.create_renewal_request(...) and returns renewal_request_id."""
        pass
    
    @abstractmethod
    def request_unpaid(self, cmd: CreateRenewalRequestCmd) -> list[int]:
        """Calls public.create_renewal_requests_for_unpaid_h(...) and returns a list of renewal_request_id."""
        pass

class IBusinessClosurePaymentRequestRepository(ABC):
    @abstractmethod
    def request_payment(self, cmd: CreateRenewalRequestCmd) -> int:
        """Calls public.create_closure_payment_request_h(...)"""
        pass

    @abstractmethod
    def request_unpaid(self, cmd: CreateRenewalRequestCmd) -> list[int]:
        """Calls public.create_closure_payment_requests_for_unpaid_h(...)"""
        pass
