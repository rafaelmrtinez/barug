# clerk/api_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from supabase_client import supabase  # ✅ you already have this wrapper in authentication/api_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from supabase_client import supabase
from django.conf import settings

API_BASE = f"{settings.TESTING_URL_USED}/api/clerk"


class GetIDValidationRequestsAPIView(APIView):
    """
    Fetches ID validation requests via Supabase RPC: get_id_validation_requests
    """

    def get(self, request):
        try:
            # ✅ Call your Supabase function
            rpc = supabase.rpc("get_id_validation_requests").execute()

            if not rpc.data:
                return Response(
                    {"message": "No ID validation requests found."},
                    status=status.HTTP_404_NOT_FOUND
                )

            return Response(
                {"data": rpc.data},
                status=status.HTTP_200_OK
            )

        except Exception as e:
            # Handle Supabase/PostgREST errors gracefully
            err_msg = str(e)
            if hasattr(e, "args") and e.args:
                first = e.args[0]
                if isinstance(first, dict) and "message" in first:
                    err_msg = first["message"]

            return Response(
                {"error": err_msg},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



class GetIDValidationRequestDetailAPIView(APIView):
    """
    Fetches one ID validation request from Supabase by verify_req_id
    """

    def get(self, request, req_id):
        try:
            # Call Supabase function but filter result
            rpc = supabase.rpc("get_id_validation_requests").execute()

            if not rpc.data:
                return Response(
                    {"message": "No ID validation requests found."},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Find the request with matching ID
            match = next((item for item in rpc.data if str(item.get("verify_req_id")) == str(req_id)), None)

            if not match:
                return Response(
                    {"message": f"No record found for verify_req_id={req_id}"},
                    status=status.HTTP_404_NOT_FOUND
                )

            return Response(
                {"data": match},
                status=status.HTTP_200_OK
            )

        except Exception as e:
            err_msg = str(e)
            if hasattr(e, "args") and e.args:
                first = e.args[0]
                if isinstance(first, dict) and "message" in first:
                    err_msg = first["message"]

            return Response(
                {"error": err_msg},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


