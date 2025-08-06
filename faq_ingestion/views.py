from rest_framework import status
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser


from dependency_injector.wiring import inject, Provide


from src.app.bootstrap.app_containers import AppContainer
from src.app.pipelines.faq_ingestion_pipeline import FAQIngestionPipeline
from src.infra.exceptions.data_access_exception import DataAccessException
from src.infra.exceptions.general_infra_exception import InfrastructureException

from barug.constants import INTENAL_ERROR
from faq_ingestion.serializers.faq_doc import FAQDocumentSerializer


# Create your views here.
class FAQIngestionView(APIView):

    parser_classes = [MultiPartParser, FormParser]
    
    @inject
    def post(self, request: Request, pipeline: FAQIngestionPipeline = Provide[AppContainer.faq_ingestion_pipeline]) -> Response:
        serializer = FAQDocumentSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            result = pipeline.exec(
                file=serializer.validated_data['file'],
                time=serializer.validated_data['created_at']
            )
            
            # I WILL REPLACE THIS WITH THE ACTUAL IMPLEMENTATION OF LOGGING.
            # FOR NOW, INTERNAL MATTERS WILL BE LOGGED USING PRINT STATEMENTS.
        except DataAccessException as e:
            print(f"DataAccessException: {str(e)}")
            return Response({"error": INTENAL_ERROR}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except InfrastructureException as e:
            print(f"InfrastructureException: {str(e)}")
            return Response({"error": INTENAL_ERROR}, status=e.status_code)
        
        if not result:
            return Response({"error": "Failed to ingest FAQ document"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({"message": "FAQ ingestion successful"}, status=status.HTTP_200_OK)