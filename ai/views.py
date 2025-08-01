from django.conf import settings
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response

from ai.serializers.chat import ChatSerializer
from src.app.services.llm import LLMService
from src.infra.services.groq import GroqService

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
    
    def post(self, request: Request) -> Response:
        
        serializer = ChatSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        
        services = LLMService(
            chat=GroqService(
                api_key=settings.AI_API_KEY,
                model=settings.AI_MODEL,
            )
        )
        
        response = services.chat_with_llm(
            prompt=serializer.validated_data['prompt']
        )
        
        # Logic for processing the chat message and generating a response goes here
        return Response({"message": response}, status=200)