from src.app.contracts.service import IService
from src.core.contracts.infra.repository.household_search_repository import IHouseholdSearchRepository


class FamilySelectionService(IService):
    
    def __init__(self, repo: IHouseholdSearchRepository):
        self.repo = repo
        
        
    def execute(self, **kwargs):
        household_id = kwargs.get('household_id', None)
        if not household_id:
            return None
        return self.repo.get(household_id)