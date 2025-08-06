from src.app.pipelines.faq_ingestion_pipeline import FAQIngestionPipeline


from django.core.files.uploadedfile import InMemoryUploadedFile


class DocumentService:
    
    def __init__(self, faq_ingestion_pipeline: FAQIngestionPipeline):
        self._faq_ingestion_pipeline = faq_ingestion_pipeline
        
    def exec_faq_pipeline(self, file: InMemoryUploadedFile, time: str):
        return self._faq_ingestion_pipeline.exec(file=file, time=time)