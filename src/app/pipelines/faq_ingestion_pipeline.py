from django.core.files.uploadedfile import InMemoryUploadedFile


from src.core.contracts.embedding import IEmbedding
from src.core.entities.faq_document import FAQDocument
from src.core.contracts.faq_repo import IFAQEntriesRepository
from src.infra.repository.document_repository import IDocumentRepository


class FAQIngestionPipeline:
    
    def __init__(
        self, 
        doc_repo: IDocumentRepository, 
        faq_entry_repo: IFAQEntriesRepository,
        embedding: IEmbedding
        ):
        
        self._doc_repo = doc_repo
        self._faq_entry_repo = faq_entry_repo
        self._embedding = embedding
        
        
    def exec(self, file: InMemoryUploadedFile, time: str):
        domain = FAQDocument(
            name=file.name,
            file=file,
            created_at=time
        )
        result = domain.process_content()
        embeddings = self._embedding.generate_batch_embedding([i[1] for i in result])
        faq_entries = [
            {
                "question": question,
                "answer": answer,
                "embedding": embedding,
                "document_id": None
            }
            for (question, answer), embedding in zip(result, embeddings)
        ]
        repo_result = self._doc_repo.insert_faq_document(
            file_name=file.name,
            total_faqs=len(faq_entries),
            uploader="padre@galaxy.com"
            ).data[0]['id']
        for entry in faq_entries:
            entry['document_id'] = repo_result
        faq_entry_result = self._faq_entry_repo.insert_bulk_faq_entries(faq_entries)
