from typing import List
from pprint import pprint
from src.app.dto.semantic_search import SemanticSearchDTO


class RAGPipelineUtils:
    """
    Utility class for RAG pipeline operations.
    """
    
    @staticmethod
    def extract_larger_content(query: str, top_k: List[SemanticSearchDTO]) -> str:
        
        context_str = ""
        
        for i in range(len(top_k)):
            context_str += f"Top {i+1} Result\n- Question: {top_k[i].question}\n- Answer: {top_k[i].answer}\n\n"
        
        path = 'src/app/pipelines/prompts/prompt.txt'
        result = None
        
        with open(path, 'r') as file:
            template = file.read()
            result = template.format(query=query, context=context_str)
            
        return result if result else ""

    @staticmethod
    def extract_top_k_content(data: dict) -> List[SemanticSearchDTO]:
        """
        Extracts top-k content from the semantic search results.
        """
        dto_list = []
        for i in range(len(data)):
            dto_list.append(
                SemanticSearchDTO(
                    question=data[i]['question'],
                    answer=data[i]['answer']
                )
            )
        return dto_list