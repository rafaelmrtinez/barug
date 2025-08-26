from rest_framework import status
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response


from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited
from django.utils.decorators import method_decorator

from dependency_injector.wiring import inject, Provide


from ai.serializers.chat import ChatSerializer


from src.core.contracts.app.pipeline import IPipeline
from barug.utils.rate_limiter import CustomRateLimiter
from src.app.bootstrap.app_containers import AppContainer


# Create your views here.
class AIChatView(APIView):
    
    """
        Handles chat interactions with the AI LLM service.

        POST this endpoint with a JSON payload containing a "prompt" key.

        EXAMPLE REQUEST USING WEB BROWSER OR BROWSABLE API:
            {
                "prompt": "How can I report a drug abuse?"
            }

        EXAMPLE RESPONSE USING WEB BROWSER OR BROWSABLE API:
            {
                "message": "To report drug abuse, you can contact your local authorities or a helpline."
            }

        FRONTEND INTEGRATION:
            Use fetch or axios to POST to this endpoint.

            fetch('/api/chat/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: 'Hello!' })
            })

            axios.post('/api/chat/', { prompt: 'Hello!' })
                .then(res => console.log(res.data))
                
        IF THE ABOVE METHODS ARE NOT WORKING, YOU CAN TRY THIS, CALL USING THE COMPLETE URL:
            fetch('http://localhost:8000/api/chat/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: 'Hello!' })
            })
    """
    
    @method_decorator(ratelimit(key='user_or_ip', rate='10/s', block=False))
    @inject
    def post(self, request: Request, pipeline: IPipeline = Provide[AppContainer.rag_pipeline]) -> Response:
        if CustomRateLimiter.is_ratelimited(request=request):
            return Response({"error": "Rate limit exceeded. Please try again later."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        serializer = ChatSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        response = None
        response = pipeline.exec(serializer.validated_data['prompt'])
        if not response:
            return Response({"error": "No response generated."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({"message": response}, status=200)
