from rest_framework import status
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from dependency_injector.wiring import inject, Provide
from rest_framework.parsers import MultiPartParser, FormParser

from faq_ingestion.serializers.faq_doc import FAQDocumentSerializer
from src.app.bootstrap.app_containers import AppContainer
from src.app.pipelines.faq_ingestion_pipeline import FAQIngestionPipeline


# Create your views here.
class FAQIngestionView(APIView):

    parser_classes = [MultiPartParser, FormParser]
    
    @inject
    def post(self, request: Request, pipeline: FAQIngestionPipeline = Provide[AppContainer.faq_ingestion_pipeline]) -> Response:
        serializer = FAQDocumentSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        result = pipeline.exec(
            file=serializer.validated_data['file'],
            time=serializer.validated_data['created_at']
        )
        
        return Response({"message": "FAQ ingestion successful"}, status=status.HTTP_200_OK)