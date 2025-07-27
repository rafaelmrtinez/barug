from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response

# Create your views here.
class HealthCheckView(APIView):

    """
    DO NOT REMOVE THIS VIEW.
    
    This view is used to ensure that the api is up and running.
    It is not intended to be used for any other purpose.
    It is a placeholder for future metrics-related functionality.
    
    If further test are needed to fully verify the API's functionality please add them to the test suite.
    
    PLEASE AVOID EXPOSING SENSITIVE INFORMATION ABOUT THE API'S INTERNALS.
    
    DO NOT REMOVE THIS VIEW.
    
    By: raffa
    """ 
    def get(self, request: Request):
        return Response({"status": "success", "message": "Metrics retrieved successfully"}, status=200)
