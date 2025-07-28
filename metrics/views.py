from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response

# Create your views here.
class HealthCheckView(APIView):

    """
    DO NOT REMOVE THIS VIEW.
    
    This view is used to check the responsiveness of this web API. This does not gaurantee that 
    the API is functioning correctly, however, it only provides insights of wether the API
    is up and running or not.
    
    NOTE: PLEASE AVOID EXPOSING SENSITIVE INFORMATION ABOUT THE API'S INTERNALS THROUGH METRICS.
    
    By: raffa
    """ 
    def get(self, request: Request):
        return Response({"status": "success", "message": "Metrics retrieved successfully"}, status=200)
