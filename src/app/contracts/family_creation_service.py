from abc import ABC, abstractmethod


class IFamilyCreationService(ABC):
    """
    Interface for family creation service.
    This abstract base class defines the contract for services responsible for creating a family entity.
    Implementations of this interface should provide the logic for executing the family creation process
    using the provided FamilyCreationCommand.
    Methods
    -------
    execute(cmd: FamilyCreationCommand)
        Executes the family creation process using the given command object.
    Parameters
    ----------
    cmd : FamilyCreationCommand
        The command object containing all necessary data for creating a family.
    Raises
    ------
    NotImplementedError
        If the method is not implemented by a subclass.
    """
    
    @abstractmethod
    def execute(self, cmd: 'FamilyCreationCommand') -> int:
        pass

