from rest_framework import status
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response

from dependency_injector.wiring import inject, Provide


from ai.serializers.chat import ChatSerializer
from barug.constants import INTENAL_ERROR

from src.app.services.llm import LLMService
from src.app.bootstrap.app_containers import AppContainer
from src.app.exceptions.prompt_file_exception import PromptFileException
from src.infra.exceptions.data_access_exception import DataAccessException
from src.infra.exceptions.general_infra_exception import InfrastructureException


# Create your views here.
class AIChatView(APIView):
    
    """
        Handles chat interactions with the AI LLM service.

        POST this endpoint with a JSON payload containing a "prompt" key.

        Example Request Body:
            {
                "prompt": "How can I report a drug abuse?"
            }

        Example Response:
            {
                "message": "To report drug abuse, you can contact your local authorities or a helpline."
            }

        Frontend Integration:
            Use fetch or axios to POST to this endpoint.

            fetch('/api/chat/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: 'Hello!' })
            })

            axios.post('/api/chat/', { prompt: 'Hello!' })
                .then(res => console.log(res.data))
    """

    @inject
    def post(self, request: Request, llm_service: LLMService = Provide[AppContainer.llm_service]) -> Response:

        serializer = ChatSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        response = None
        
        try:
            response = llm_service.chat(serializer.validated_data['prompt'])
            
            # I WILL REPLACE THIS WITH THE ACTUAL IMPLEMENTATION OF LOGGING.
            # FOR NOW, INTERNAL MATTERS WILL BE LOGGED USING PRINT STATEMENTS.
        except PromptFileException as e:
            print(f"Prompt file error: {e}")
            return Response({"error": INTENAL_ERROR}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except DataAccessException as e:
            print(f"Data access error: {e}")
            return Response({"error": INTENAL_ERROR}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except InfrastructureException as e:
            print(f"Infrastructure error: {e}")
            return Response({"error": INTENAL_ERROR}, status=e.status_code)

        if not response:
            return Response({"error": "No response generated."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"message": response}, status=200)
