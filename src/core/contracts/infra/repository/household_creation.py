from abc import ABC, abstractmethod


class IHouseholdCreationRepository:
    
    def create_household(self, data: dict) -> dict:
        pass
    
    def find_household_by_house_number(self, house_no: str) -> int:
        pass