from django.urls import path
from .api.faq_ingest_api import FAQIngestAPI
from .api.faqs_api import FAQListAPI
from .views import faqs_page

app_name = 'doc_ingest'

API_VERSION=1

urlpatterns = [
    path(f'api/v{API_VERSION}/faq-upload/', FAQIngestAPI.as_view(), name='faq_upload'),
    path(f'api/v{API_VERSION}/faqs/', FAQListAPI.as_view(), name='faq_list'),
    # Server-rendered FAQ page
    path('faqs/', faqs_page, name='faq_page'),
]
