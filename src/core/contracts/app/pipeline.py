from abc import ABC, abstractmethod

class IPipeline(ABC):
    """
    Interface for pipeline classes.
    """

    @abstractmethod
    def exec(self, *args, **kwargs):
        """
        Run the pipeline with the given arguments.
        """
        raise NotImplementedError("Subclasses must implement this method.")