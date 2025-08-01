from src.infra.contracts.llm import ILLM


class LLMService:
    
    def __init__(self, chat: ILLM):
        self.chat = chat

    def chat_with_llm(self, prompt: str, **kwargs) -> str:
        """
        Interact with the LLM to generate a response based on the provided prompt.

        :param prompt: The input text to generate a response for.
        :param kwargs: Additional parameters for text generation.
        :return: Generated text as a string.
        """
        return self.chat.generate_text(prompt, **kwargs)