from src.app.pipelines.rag_pipeline import RAGPipeline

class LLMService:

    def __init__(self, rag_pipeline: RAGPipeline) -> None:
        self.rag_pipeline = rag_pipeline

    def chat(self, prompt: str) -> str:
        """
        Interact with the LLM to generate a response based on the provided prompt.

        :param prompt: The input text to generate a response for.
        :return: Generated text as a string.
        """
        return self.rag_pipeline.exec(prompt=prompt)