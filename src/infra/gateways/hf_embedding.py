from src.core.contracts.embedding import IEmbedding
from huggingface_hub import InferenceClient

from src.infra.exceptions.general_infra_exception import InfrastructureException

class HuggingFaceClient(IEmbedding):
    """Hugging Face client for generating embeddings."""

    def __init__(self, provider: str, api_key: str, model: str):
        self._provider = provider
        self._api_key = api_key
        self._model = model
        self._client = InferenceClient(
            provider=self._provider,
            token=self._api_key,
        )

    def generate_embedding(self, text: str) -> list[float]:
        try:
            """Generate an embedding for the given text."""
            result = self._client.feature_extraction(text, model=self._model)
            return result if isinstance(result, list) else result.tolist()
        except Exception as e:
            raise InfrastructureException(f"Error generating embedding: {str(e)}", status_code=500)

    def generate_batch_embedding(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        inputs = self.tokenizer(texts, padding=True, truncation=True, return_tensors='pt')
        outputs = self.model(**inputs)
        return outputs.last_hidden_state.mean(dim=1).tolist()