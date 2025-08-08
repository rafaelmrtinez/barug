from django.urls import path
from . import views

app_name = 'faq_ingestion'

urlpatterns = [
    path('', views.FAQIngestionView.as_view(), name='faq_ingestion'),
]
