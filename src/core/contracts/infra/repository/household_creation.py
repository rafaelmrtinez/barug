from abc import ABC, abstractmethod


class IHouseholdCreationRepository(ABC):
    
    @abstractmethod
    def create_household(self, data: dict) -> dict:
        pass
    
    @abstractmethod
    def get_existing_house_number_request(self, house_number: str) -> int:
        pass
    
    @abstractmethod
    def get_existing_request_count_by_id(self, id: str) -> int:
        pass
    
    @abstractmethod
    def get_all_household_count(self) -> int:
        pass

    @abstractmethod
    def get_existing_household_num_request(self, household_num) -> int:
        pass
    
    @abstractmethod 
    def find_household_by_house_number(self, house_no: str) -> int:
        pass