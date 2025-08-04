from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from faq_ingestion.serializers.faq_doc import FAQDocumentSerializer

# Create your tests here.
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

        response = self.client.post('/api/v1/faq-ingest/', data=data, format='multipart')
        
        serializer = FAQDocumentSerializer(data=data)
        
        if not serializer.is_valid():
            print(serializer.errors)
            self.fail("Serializer validation failed")
            
        self.assertTrue(serializer.is_valid())
        self.assertEqual(response.data, {"message": "FAQ ingestion successful"})
        self.assertEqual(response.status_code, 200)