from rest_framework import status
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser

from faq_ingestion.serializers.faq_doc import FAQDocumentSerializer


# Create your views here.
class FAQIngestionView(APIView):

    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request: Request) -> Response:
        """
        Handle POST requests to ingest FAQs.
        """
        serializer = FAQDocumentSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({"message": "FAQ ingestion successful"}, status=status.HTTP_200_OK)