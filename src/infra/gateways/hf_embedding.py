import requests


from huggingface_hub import InferenceClient


from src.core.contracts.embedding import IEmbedding
from src.infra.exceptions.general_infra_exception import InfrastructureException


class HuggingFaceClient(IEmbedding):
    """Hugging Face client for generating embeddings."""

    def __init__(
        self, 
        provider: str, 
        api_key: str, 
        model: str, 
        url: str
        ):
        self._provider = provider
        self._api_key = api_key
        self._model = model
        self._client = InferenceClient(
            provider=self._provider,
            token=self._api_key,
        )
        self.url = url
        self._headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json"
        }

    def generate_embedding(self, text: str) -> list[float]:
        try:
            """Generate an embedding for the given text."""
            result = self._client.feature_extraction(text, model=self._model)
            return result if isinstance(result, list) else result.tolist()
        except Exception as e:
            raise InfrastructureException(f"Error generating embedding: {str(e)}", status_code=500)

    def generate_batch_embedding(self, payload: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        payload = {"inputs": payload}
        try:
            response = requests.post(
                self.url,
                headers=self._headers,
                json=payload
            )
        except requests.RequestException as e:
            raise InfrastructureException(f"Error making request to Hugging Face: {str(e)}", status_code=500)
        
        if not response.ok or response.status_code != 200:
            raise InfrastructureException(f"Error generating batch embeddings: {embeddings.text}", status_code=embeddings.status_code)
        
        embeddings = response.json()
        
        if not embeddings:
            raise InfrastructureException("Invalid embeddings format from Hugging Face API.", status_code=500)
        
        if not isinstance(embeddings, list):
            raise InfrastructureException("Expected a list of embeddings from Hugging Face API.", status_code=500)

        return embeddings