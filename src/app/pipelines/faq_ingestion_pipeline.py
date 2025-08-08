from django.core.files.uploadedfile import InMemoryUploadedFile


from src.core.contracts.embedding import IEmbedding
from src.core.contracts.app.pipeline import IPipeline
from src.core.entities.faq_document import FAQDocument
from src.core.contracts.faq_repo import IFAQIngestionRepository

class FAQIngestionPipeline(IPipeline):
    
    def __init__(
        self, 
        faq_entry_repo: IFAQIngestionRepository,
        embedding: IEmbedding
        ):
        self._faq_entry_repo = faq_entry_repo
        self._embedding = embedding
        
        
    def exec(self, file: InMemoryUploadedFile, time: str):
        result = self.__faq_entry_business_logic(file, time)
        embeddings = self.__generate_batch_embeddings(result)
        faq_entries = self.__build_faq_entries(result, embeddings)
        repo_result = self.__doc_insertion(file, faq_entries)
        self.__entries_doc_id_insertion(faq_entries, repo_result)
        document_id = self.__entries_insertion(faq_entries)
        return document_id

    def __entries_insertion(self, faq_entries):
        document_id = self._faq_entry_repo.insert_bulk_faq_entries(faq_entries)
        return document_id

    def __entries_doc_id_insertion(self, faq_entries, repo_result):
        for entry in faq_entries:
            entry['document_id'] = repo_result

    def __doc_insertion(self, file, faq_entries):
        repo_result = self._faq_entry_repo.insert_faq_document(
            file_name=file.name,
            total_faqs=len(faq_entries),
            uploader="padre@galaxy.com"
            )
        return repo_result

    def __build_faq_entries(self, result, embeddings):
        faq_entries = [
            {
                "question": question,
                "answer": answer,
                "embedding": embedding,
                "document_id": None
            }
            for (question, answer), embedding in zip(result, embeddings)
        ]
        
        return faq_entries

    def __generate_batch_embeddings(self, result):
        payload = [i[1] for i in result]
        embeddings = self._embedding.generate_batch_embedding(payload=payload)
        return embeddings

    def __faq_entry_business_logic(self, file, time):
        domain = FAQDocument(
            name=file.name,
            file=file,
            created_at=time
        )
        result = domain.process_content()
        return result
