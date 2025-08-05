from io import BytesIO
import os
from pprint import pprint
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from faq_ingestion.serializers.faq_doc import FAQDocumentSerializer
from django.core.files.uploadedfile import InMemoryUploadedFile

from src.core.enums.faq_doc_extensions import FAQDocExtensions


# Create your tests here.
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

        pair = set()
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

    def test_openpyxl_xlsxl_file(self):
        from openpyxl import load_workbook
        
        workbook = load_workbook(filename=self.fake_file)
        sheet = workbook.active

        allowed_headers = ['question', 'answer']
        headers = [cell.value.lower() for cell in sheet[1]]

        for i in range(len(headers)):
            if headers[i] not in allowed_headers:
                self.fail(f"Header '{headers[i]}' is not allowed. Allowed headers are: {allowed_headers}")
        
        
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
            self.fail(f"Unsupported content type: {self.fake_file.content_type}")

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
