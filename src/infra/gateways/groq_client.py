from src.core.contracts.llm import ILLM

from groq import Groq

from src.infra.exceptions.general_infra_exception import InfrastructureException

class GroqClient(ILLM):
    
    def __init__(self, api_key: str, model: str):
        self._api_key = api_key
        self._model = model
        self._client: Groq = Groq(api_key=self._api_key)
        
    def __message_template(self, prompt: str) -> dict:
        """
        Create a message template for the Groq model.

        :param prompt: The input text to generate a response for.
        :return: A dictionary representing the message template.
        """
        return {
            "role": "user",
            "content": prompt,
        }
        
    def generate_text(self, prompt: str, **kwargs) -> str:
        """
        Generate text using the Groq model based on the provided prompt.

        :param prompt: The input text to generate a response for.
        :param kwargs: Additional parameters for text generation.
        :return: Generated text as a string.
        """
        response = self.__fetch_model_response(prompt)
        return response

    def __fetch_model_response(self, prompt) -> str:
        try:
            response = self._client.chat.completions.create(
                messages=[self.__message_template(prompt)],
                model=self._model,
            )
            
            return response.choices[0].message.content
        except Exception as e:
            raise InfrastructureException(f"Error generating text: {str(e)}", status_code=500)
    
    def get_model_info(self) -> dict:
        """
        Retrieve information about the Groq model.

        :return: A dictionary containing model information.
        """
        return {
            "model_name": self._client.model_name,
            "version": self._client.version,
            "api_key": self._api_key
        }