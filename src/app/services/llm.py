from src.core.contracts.llm import ILLM
from dependency_injector.wiring import Provide, inject


class LLMService:

    @inject
    def __init__(self, chat: ILLM) -> None:
        self.chat = chat

    def chat_with_llm(self, prompt: str, **kwargs) -> str:
        """
        Interact with the LLM to generate a response based on the provided prompt.

        :param prompt: The input text to generate a response for.
        :param kwargs: Additional parameters for text generation.
        :return: Generated text as a string.
        """
        return self.chat.generate_text(prompt, **kwargs)