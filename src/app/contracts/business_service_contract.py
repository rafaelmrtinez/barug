from abc import ABC, abstractmethod

from typing import Any, Dict, List, Optional, Tuple

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
        search: Optional[str],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, List[tuple[str, str]]], Optional[str]]:
        """
        Returns:
          rows:    filtered resident rows (to pick as business owners)
          choices: {'sex': [...], 'status': [...]}
          error:   error string if something failed, else None
        """
        pass