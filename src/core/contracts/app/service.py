from abc import ABC, abstractmethod


class FamilyMembershipService(ABC):

    @abstractmethod
    def execute(
        self,
        resident_id: int,
        household_id: int,
        family_id: int,
        household_head_relationship: int,
        family_head_relationship: int,
        residency_period: int
    ) -> str:
        """This method is used to execute and perform orchestration
        at the application level to different repositories and domain
        to enforce business rules and CRUD operations.

        Args:
            resident_id (int): _description_
            household_id (int): _description_
            family_id (int): _description_
            household_head_relationship (int): _description_
            family_head_relationship (int): _description_
            residency_period (int): _description_

        Returns:
            str: _description_
        """
