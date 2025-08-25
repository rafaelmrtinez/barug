from abc import ABC, abstractmethod

class IFamilyCreationRepository(ABC):
    """
    Interface for family creation repository operations.
    Defines methods for creating and retrieving family unit data.
    """
    
    def find_existing_family_number_request(self, ufc_number: str):
        pass

    def insert_family_unit(self, persistence: 'FamilyCreationPersistence'):
        pass
        
    def get_existing_family_number_request_count(self, family_number: str):
        pass

    def find_pending_request(self, requester_id: int) -> int:
        pass

    def get_all_family_count(self):
        pass
    
    def get_family_count_by_household_id(self, id):
        pass
    
    def get_resident_by_id(self, id: str) -> "Resident":
        pass
    
    def get_household_info_by_house_num(self, house_num: str) -> "HouseholdInformationDTO":
        pass

    def find_resident_family_unit_if_exist(self, id):
        pass