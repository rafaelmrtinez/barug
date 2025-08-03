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
    When using this API in the frontend, please make sure to include the DOMAIN in the request URL.
    
    Example URL: http://api-domain.com/api/v1/ai/c/
    
    Please ensure that correct headers are set for requests, especially for JSON content type and JWT.
    The method expects a POST request with a JSON body containing the 'prompt' field.
        
    For fetch API:
    fetch('http://localhost:8000/api/v1/ai/c/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer YOUR_JWT_TOKEN'
        },
        body: JSON.stringify({ prompt: 'Your question here' })
    })
    
    For axios:
    axios.post('http://localhost:8000/api/v1/ai/c/', {
        prompt: 'Your question here'
    }, {
        headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer YOUR_JWT_TOKEN'
        }
    })

    Example Usage:
    POST /api/v1/ai/c/
    {
        "prompt": "How to request a barangay clearance?"
    }

    Example Response:
    {
        "message": "To request a Barangay Clearance, you can follow these steps:\n\n1. Visit the Barangay Hall in your area, as this is where you can initiate the process.\n2. Once you're at the Barangay Hall, fill out the application form provided by the staff.\n \n- Required documents typically include:\n  - A valid ID for identification purposes\n  - Proof of residence to confirm you live in the barangay\n  - Sometimes, a community tax certificate (cedula) may also be required\n\n3. After completing the form and gathering the necessary documents, proceed to pay the required fee.\n4. Submit your application along with the supporting documents and wait for the clearance to be processed.\n\nPlease note that requirements might vary slightly depending on the barangay, so it's a good idea to call ahead or check with the Barangay Hall staff to confirm what you need to bring."
    }
    """
    @inject
    def post(self, request: Request, llm_service: LLMService = Provide[AppContainer.llm_service]) -> Response:

        serializer = ChatSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        response = llm_service.chat(serializer.validated_data['prompt'])

        # Logic for processing the chat message and generating a response goes here
        return Response({"message": response}, status=200)
