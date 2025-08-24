from rest_framework import status
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser


from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator
from dependency_injector.wiring import inject, Provide


from src.app.contracts.pipeline import IPipeline
from src.app.bootstrap.app_containers import AppContainer


from barug.utils.rate_limiter import CustomRateLimiter


from faq_ingestion.serializers.faq_doc import FAQDocumentSerializer


# Create your views here.
class FAQIngestionView(APIView):

    """
        Handles the ingestion of FAQ documents.
        Only type of excel files are supported.
        
        To be able to use this endpoint, make sure
        that Question and Answer columns are present
        in the excel file as headers.
        
        POST this endpoint with a file payload containing the FAQ document.
        
        You can use the following parameters when making a POST request:
        - file: The FAQ document to be ingested (must be an Excel file).
        - created_at: The timestamp when the document was created (optional, defaults to current time).
        
    Returns:
        _type_: Response
        - 200: If the ingestion is successful.
        - 400: If the request data is invalid.
        - 500: If there is an internal server error.
    """

    parser_classes = [MultiPartParser, FormParser]
    
    @method_decorator(ratelimit(key='user_or_ip', rate='10/s', block=False))
    @inject
    def post(self, request: Request, pipeline: IPipeline = Provide[AppContainer.faq_ingestion_pipeline]) -> Response:
        if CustomRateLimiter.is_ratelimited(request=request):
            return Response({"error": "Rate limit exceeded. Please try again later."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        serializer = FAQDocumentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        result = pipeline.exec(
            file=serializer.validated_data['file'],
            time=serializer.validated_data['created_at']
        )
        if not result:
            return Response({"error": "Failed to ingest FAQ document"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({"message": "FAQ ingestion successful"}, status=status.HTTP_200_OK)