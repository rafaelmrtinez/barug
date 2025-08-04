from rest_framework import status
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response


# Create your views here.
class FAQIngestionView(APIView):
    
    def post(self, request: Request) -> Response:
        """
        Handle POST requests to ingest FAQs.
        """
        return Response({"message": "FAQ ingestion successful"}, status=status.HTTP_200_OK)