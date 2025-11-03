from django.urls import path
from .api.faq_ingest_api import FAQIngestAPI

app_name = 'doc_ingest'

urlpatterns = [
    path('api/faq-upload/', FAQIngestAPI.as_view(), name='faq_upload'),
]
