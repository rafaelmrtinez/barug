from attr import dataclass
from pydantic import BaseModel

@dataclass(frozen=True)
class SemanticSearchDTO(BaseModel):
    """
    Data Transfer Object for semantic search requests.
    
    Attributes:
        query (str): The search query string.
        limit (int): The maximum number of results to return.
    """
    question: str
    answer: str