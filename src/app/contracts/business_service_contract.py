from abc import ABC, abstractmethod

from typing import Any, Dict, List, Optional, Tuple
from decimal import Decimal
from src.app.transfer_objects.commands.business_cmd import (
  RegisterBusinessProfileCmd,
  CreateRenewalRequestCmd,
)
from src.app.transfer_objects.dto.business_dto import (
  ResidentOwnerDTO,
  NonResidentOwnerDTO,
  OwnerBusinessDTO,
  RenewalQuoteLineDTO
)  

# from supabase_auth import Optional

class IBusinessService(ABC):
    @abstractmethod
    def execute(self, 
        search:Optional[str], 
        b_category: Optional[int] , 
        ownership_type:Optional[int], 
        status:Optional[int]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, List[tuple[str, str]]], Optional[str]]:
        """
        Returns:
          rows:    filtered business rows
          choices: {'b_category': [...], 'ownership_type': [...], 'status': [...]}
          error:   error string if something failed, else None
        """
        pass
    
class IResidentOwnerService(ABC):
    @abstractmethod
    def execute(
      self,
      search: Optional[str] = None,
    ) -> list[ResidentOwnerDTO]:
        """
        Returns:
          rows:    filtered resident rows (to pick as business owners)
          error:   error string if something failed, else None
        """
        pass
    
    @abstractmethod
    def get_owner_details(
      self,
      person_id: Optional[int],
    ) -> Optional[ResidentOwnerDTO]:
      """Fetch full details of a single owner."""
      pass

class INonResidentOwnerService(ABC):
    @abstractmethod
    def execute_insert_owner_details(self, cleaned_data: Dict[str, Any], added_by_id: int) -> NonResidentOwnerDTO:
        """
        Map form.cleaned_data -> command -> repo.insert_owner_details.
        Raise a ValueError (or domain error) on duplicates/validation problems.
        """
        pass
    
class IBusinessRegistrationService(ABC):
    @abstractmethod
    def business_registration(self, cmd: RegisterBusinessProfileCmd) -> tuple[int, int]:
      pass

class IBusinessInfoService(ABC):
    @abstractmethod
    def execute(self, person_id: int, business_id: int) -> OwnerBusinessDTO:
        pass
    
    @abstractmethod
    def execute_by_business_id(self, business_id: int) -> OwnerBusinessDTO:
        pass
    
class IBusinessMapService(ABC):
    @abstractmethod
    def execute(
      self,
      search:Optional[str], 
      b_category: Optional[str] , 
      ownership_type:Optional[str], 
      status:Optional[str]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, List[tuple[str, str]]], Optional[str]]:
        pass

class IBusinessRenewalService(ABC):
    @abstractmethod
    def execute(self, 
        search:Optional[str], 
        clearance_state: Optional[int] , 
    ) -> Tuple[List[Dict[str, Any]], Dict[str, List[tuple[str, str]]], Optional[str]]:
        pass
    
class IBusinessRenewalQuoteService(ABC):
    @abstractmethod
    def execute(self, business_id: int, year: int) -> Tuple[Decimal, List[RenewalQuoteLineDTO], List[Dict[str, Any]]]:
        """
        Returns:
          grand_total      : Decimal
          quote_rows       : List[RenewalQuoteLineDTO]
          paid_history_rows: List[{period_year, or_number, paid_on}]
        """
        pass
    
class IBusinessRenewalRequestService(ABC):
    @abstractmethod
    def request_renewal(self, cmd: CreateRenewalRequestCmd) -> int:
        pass
    
    @abstractmethod
    def request_unpaid(self, cmd: CreateRenewalRequestCmd) -> list[int]:
        pass
