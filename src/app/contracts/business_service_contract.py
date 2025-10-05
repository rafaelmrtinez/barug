from abc import ABC, abstractmethod

from typing import Any, Dict, List, Optional, Tuple
from src.app.transfer_objects.dto.business_dto import (
  ResidentOwnerDTO,
  NonResidentOwnerDTO
)  

# from supabase_auth import Optional

class IBusinessService(ABC):
    @abstractmethod
    def execute(self, 
        search:Optional[str], 
        b_type: Optional[str] , 
        ownership_type:Optional[str], 
        status:Optional[str]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, List[tuple[str, str]]], Optional[str]]:
        """
        Returns:
          rows:    filtered business rows
          choices: {'b_type': [...], 'ownership_type': [...], 'status': [...]}
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