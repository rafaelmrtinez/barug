from django.conf import settings
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response

from ai.serializers.chat import ChatSerializer
from src.app.services.llm import LLMService
from dependency_injector.wiring import inject, Provide
from src.app.bootstrap.app_containers import AppContainer

# Create your views here.
class AIChatView(APIView):
    """
    AI Chat View for handling chat interactions.
    
    This view is responsible for processing chat messages and returning AI-generated responses.
    
    Example usage:
    POST /api/ai/chat/
    {
        "prompt": "Hello, how are you?"
    }
    
    Response:    {
        "message": "I'm doing well, thank you!"
    }
    """
    @inject
    def post(self, request: Request, llm_service: LLMService = Provide[AppContainer.llm_service]) -> Response:

        serializer = ChatSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        
        response = llm_service.chat_with_llm(serializer.validated_data['prompt'])
        
        # Logic for processing the chat message and generating a response goes here
        return Response({"message": response}, status=200)