from typing import Any, Dict, List, Optional, Tuple
from dataclasses import asdict

from src.app.transfer_objects.dto.business_dto import BusinessListDTO
from src.app.contracts.business_service_contract import IBusinessService
from src.domain.contracts.business_repository_contract import IBusinessRepository

from src.app.transfer_objects.dto.business_dto import ResidentOwnerDTO
from src.app.contracts.business_service_contract import IResidentOwnerService
from src.domain.contracts.business_repository_contract import IResidentOwnerRepository

class BusinessService(IBusinessService): 
    def __init__(
        self,
        business_repository: IBusinessRepository,
    ):
        self._business_repo = business_repository

    def execute(
        self,
        search: Optional[str] = None,
        b_type: Optional[str] = None,
        ownership_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[BusinessListDTO]:
        if search:
            return self._business_repo.search_business(search)
        if b_type is not None:
            return self._business_repo.sort_b_type(b_type)
        if ownership_type is not None:
            return self._business_repo.sort_ownership_type(ownership_type)
        if status is not None:
            return self._business_repo.sort_status(status)
        
        return self._business_repo.fetch_business_list()
    
class ResidentOwnerService(IResidentOwnerService):
    def __init__(
        self,
        resident_owner_repository: IResidentOwnerRepository,
    ):
        self._residentowner_repo = resident_owner_repository

    def execute(
        self, 
        search: Optional[str] = None, 
    ) -> list[ResidentOwnerDTO]:
        if not search or not str(search).strip():
            return []
        return self._residentowner_repo.search_owner(search=search.strip())

