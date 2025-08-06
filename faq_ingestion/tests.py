from io import BytesIO
import os
from pprint import pprint
from pydoc import text
from typing import List, Set
from django.test import TestCase
from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.files.uploadedfile import SimpleUploadedFile
import requests
from src.infra.repository.document_repository import DocumentRepository
from src.infra.repository.faq_ingestion_repository import FAQEntriesRepository
from supabase_client_dev import supabase

from faq_ingestion.serializers.faq_doc import FAQDocumentSerializer
from src.core.enums.faq_doc_extensions import FAQDocExtensions
from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.infra.gateways.hf_embedding import HuggingFaceClient
from postgrest.exceptions import APIError as PostgrestAPIError


# Create your tests here.
class FAQIngestionServiceTestCase(TestCase):

    def setUp(self):
        self.fake_file_bytes = None
        with open(os.path.join(settings.BASE_DIR, 'test_data.xlsx'), 'rb') as f:
            self.fake_file_bytes = BytesIO(f.read())

        self.file: InMemoryUploadedFile = InMemoryUploadedFile(
            file=self.fake_file_bytes,
            field_name='file',
            name='test_data.xlsx',
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            size=self.fake_file_bytes.getbuffer().nbytes,
            charset=None
        )

    def test_exec_faq_ingestion(self):
        from src.core.entities.faq_document import FAQDocument
        domain = FAQDocument(
            name=self.file.name,
            file=self.file,
            created_at='2023-10-01T00:00:00Z'
        )
        result = domain.process_content()
        hf_client = HuggingFaceClient(
            provider=settings.HF_PROVIDER,
            api_key=settings.HF_API_KEY,
            model=settings.HF_MODEL,
            url=settings.HF_URL
        )
        embeddings = hf_client.generate_batch_embedding([i[1] for i in result])
        faq_entries = [
            {
                "question": question,
                "answer": answer,
                "embedding": embedding,
                "document_id": None
            }
            for (question, answer), embedding in zip(result, embeddings)
        ]
        doc_repo = DocumentRepository(supabase_adapter=supabase)
        faq_entries_repo = FAQEntriesRepository(supabase_adapter=supabase)
        repo_result = doc_repo.insert_faq_document(
            file_name=self.file.name,
            total_faqs=len(faq_entries),
            uploader="padre@galaxy.com"
            ).data[0]['id']
        
        for entry in faq_entries:
            entry['document_id'] = repo_result
        
        pprint(f"Document ID: {repo_result}")
        faq_entry_result = faq_entries_repo.insert_bulk_faq_entries(faq_entries)
        print(f"Document Insert Result: {repo_result}")

class FAQIngestionFAQEntryUploadTestCase(TestCase):

    def setUp(self):
        pass

    # def test_faq_entry_repo(self):

    #     # print(self.mock_data[0])
    #     # print(self.mock_data[0][0])
    #     # print(self.mock_data[0][1])
    #     # print(self.mock_data[0][2])

    #     try:
    #         response = self.supabase_adapter.table('faq_entry').insert(self.mock_data).execute()
    #         print(f"Response: {response.data}")

    #     except PostgrestAPIError as e:
    #         print(f"Error: {e}")


class FAQIngestionRepositoryTestCase(TestCase):

    def setUp(self):
        with open(os.path.join(settings.BASE_DIR, 'test_data.xlsx'), 'rb') as f:
            self.file: InMemoryUploadedFile = InMemoryUploadedFile(
                file=f,
                field_name='file',
                name='test_data.xlsx',
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                size=os.path.getsize(os.path.join(
                    settings.BASE_DIR, 'test_data.xlsx')),
                charset=None
            )
        self.uploader = "test@test.com"

    # def test_repo(self):
    #     client = supabase
    #     resp = client.table('faq_document').insert({
    #         "title": self.file.name,
    #         "total_faqs": int(self.file.size / 2),
    #         "uploaded_by": self.uploader
    #     }).execute()

    #     print(f"Response: {resp}")


class FAQIngestionEmbeddingTestCase(TestCase):
    def setUp(self):
        self.faq_pairs: List[tuple[str, str]] = [
            ("Sample question 1", "Sample answer 1"),
            ("Sample question 2", "Sample answer 2"),
            ("Sample question 3", "Sample answer 3")
        ]

        self.embeddings = [
            'Sample embedding 1',
            'Sample embedding 2',
            'Sample embedding 3'
        ]

        self.client: HuggingFaceClient = HuggingFaceClient(
            provider=settings.HF_PROVIDER,
            api_key=settings.HF_API_KEY,
            model=settings.HF_MODEL,
            url=settings.HF_URL
        )

    # DO NOT UNCOMMENT UNLESS YOU NEED TO TEST THE ACTUAL API CALL!
    # IT IS ADVISABLE TO MOCK THE API CALLS IN UNIT TESTS.
    # def test_hf_client(self):
    #     payload = [i[1] for i in self.faq_pairs]
    #     # print(f"Payload: {payload}")
    #     result = self.client.generate_batch_embedding(payload)

    #     faq_entries = [
    #         {
    #             "question": question,
    #             "answer": answer,
    #             "embedding": embedding
    #         }
    #         for (question, answer), embedding in zip(self.faq_pairs, result)
    #     ]

    #     print(f"\n\n\nFAQ Pairs: {faq_entries}\n\n\n")

    def test_generate_batch_embedding(self) -> list[list[float]]:
        if not self.embeddings or not isinstance(self.embeddings, list):
            self.fail("Invalid response format from Hugging Face API.")

        faq_entries = [
            {
                "question": question,
                "answer": answer,
                "embedding": embedding
            }
            for (question, answer), embedding in zip(self.faq_pairs, self.embeddings)
        ]

        self.assertGreater(len(faq_entries), 0, "No valid FAQ entries found.")
        self.assertTrue(all(isinstance(entry, dict)
                        for entry in faq_entries), "All entries should be dictionaries.")
        self.assertTrue(all("question" in entry for entry in faq_entries),
                        "All entries should have a 'question' key.")
        self.assertTrue(all("answer" in entry for entry in faq_entries),
                        "All entries should have an 'answer' key.")


class FAQDocumentDomainTestCase(TestCase):
    def setUp(self):
        self.max_file_size_mb = 5
        self.file_max_size = self.max_file_size_mb * 1024 * 1024
        self.allowed_mimes = [
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-excel',
        ]
        self.allowed_extensions = [ext.value for ext in FAQDocExtensions]
        self.fake_file_path = os.path.join(settings.BASE_DIR, 'test_data.xlsx')
        self.fake_file_bytes: BytesIO = None
        self.fake_file_name = 'test_data.xlsx'
        self.fake_content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        with open(self.fake_file_path, 'rb') as f:
            self.fake_file_bytes = BytesIO(f.read())
        self.fake_file = InMemoryUploadedFile(
            file=self.fake_file_bytes,
            field_name='file',
            name=self.fake_file_name,
            content_type=self.fake_content_type,
            size=1024 * 1024,
            charset=None
        )

    def test_pandas_read_excel(self):
        import pandas as pd
        from io import BytesIO

        bytes_data = BytesIO(self.fake_file.read())
        df = pd.read_excel(bytes_data, engine='openpyxl')

        required_headers = ['question', 'answer']
        headers = df.columns.str.lower().tolist()

        missing_headers = set(required_headers) - set(headers)
        if missing_headers:
            self.fail(f"Missing required headers: {missing_headers}")

        unexpected_headers = set(headers) - set(required_headers)
        if unexpected_headers:
            self.fail(f"Unexpected headers: {unexpected_headers}")

        if df.empty:
            self.fail("Uploaded file is empty.")

        faq_pair = []
        for i, row in df.iterrows():
            question = str(row.get('question', '')).strip()
            answer = str(row.get('answer', '')).strip()

            if not question:
                self.fail(f"Row {i+2} is empty or has no data.")

            if not answer:
                self.fail(f"Row {i+2} has no answer.")

            pair = (question, answer)

            if len(question) > 300:
                self.fail(f"Row {i+2} question exceeds 300 characters limit.")

            if len(answer) > 1000:
                self.fail(f"Row {i+2} answer exceeds 1000 characters limit.")

            if isinstance(row['question'], float) or isinstance(row['answer'], float):
                self.fail(f"Row {i+2}: FAQ contains invalid numeric values.")

            faq_pair.append(pair)

        self.assertGreater(
            len(faq_pair), 0, "No valid FAQ pairs found in the file.")

    def test_openpyxl_xlsxl_file(self):
        from openpyxl import load_workbook

        workbook = load_workbook(filename=self.fake_file)
        sheet = workbook.active

        allowed_headers = ['question', 'answer']
        headers = [cell.value.lower() for cell in sheet[1]]

        for i in range(len(headers)):
            if headers[i] not in allowed_headers:
                self.fail(
                    f"Header '{headers[i]}' is not allowed. Allowed headers are: {allowed_headers}")

    def test_faq_mime_types_enum(self):
        from src.core.enums.faq_doc_mimes import FAQDocMimeTypes
        allowed_mimes = FAQDocMimeTypes.get_allowed_mimes()

        self.assertIsNotNone(allowed_mimes)

    def test_domain_model_initialization(self):
        from src.core.entities.faq_document import FAQDocument
        domain = FAQDocument(
            name=self.fake_file.name,
            file=self.fake_file,
            created_at='2023-10-01T00:00:00Z'
        )
        self.assertEqual(domain.name, self.fake_file.name)
        if not isinstance(domain, FAQDocument):
            self.fail("Domain model is not an instance of FAQDocument")

    def test_file_validation(self):
        if self.fake_file is None:
            self.fail("No file content to process.")

        if self.fake_file.size < 1:
            self.fail("File is empty.")

        if self.fake_file.size > self.file_max_size:
            self.fail(
                f"File size exceeds the maximum limit of {self.max_file_size_mb} bytes.")

        file_ext = self.fake_file.name.split('.')[-1].lower()
        if file_ext not in self.allowed_extensions:
            self.fail(f"Unsupported file extension: {file_ext}")

        if self.fake_file.content_type not in self.allowed_mimes:
            self.fail(
                f"Unsupported content type: {self.fake_file.content_type}")


class FAQIngestionViewTestCase(TestCase):

    def test_view_response(self):
        # Mimic a POST request object that contains excel file
        fake_file = SimpleUploadedFile(
            name='test_faqs.xlsx',
            content=b'Excel file content',
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        data = {
            'file': fake_file
        }
        response = self.client.post(
            '/api/v1/faq-ingest/', data=data, format='multipart')
        serializer = FAQDocumentSerializer(data=data)
        if not serializer.is_valid():
            self.fail("Serializer validation failed")
        self.assertTrue(serializer.is_valid())
        self.assertEqual(
            response.data, {"message": "FAQ ingestion successful"})
        self.assertEqual(response.status_code, 200)
