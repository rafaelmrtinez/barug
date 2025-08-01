from abc import ABC, abstractmethod


class ILLM(ABC):
    """
    Interface for a Language Model (LLM) that defines the contract for LLM implementations.
    """

    @abstractmethod
    def generate_text(self, prompt: str, **kwargs) -> str:
        """
        Generate text based on the provided prompt.

        :param prompt: The input text to generate a response for.
        :param kwargs: Additional parameters for text generation.
        :return: Generated text as a string.
        """
        pass

    @abstractmethod
    def get_model_info(self) -> dict:
        """
        Retrieve information about the LLM model.

        :return: A dictionary containing model information.
        """
        pass