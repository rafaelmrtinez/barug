from abc import ABC, abstractmethod


class IEmbedding(ABC):
    
    """Interface for embedding generation."""
    
    @abstractmethod
    def generate_embedding(self, text: str) -> list[float]:
        """Generate an embedding for the given text."""
        pass

    @abstractmethod
    def generate_batch_embedding(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        pass