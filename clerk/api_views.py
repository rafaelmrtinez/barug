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
from .serializers import ApprovePersonByClerkSerializer

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



class ApprovePersonByClerkAPIView(APIView):
    def post(self, request, req_id=None):
        print("📥 Raw request.data:", request.data)

        incoming = request.data.copy()
        if req_id is not None:
            incoming["request_id"] = req_id
        print("📥 Incoming+URL:", incoming)

        # normalize keys
        keymap = {
            "p_clerk_staff_id": "clerk_staff_id",
            "p_person_id":      "person_id",
            "p_request_id":     "request_id",
            "p_status_id":      "status_id",
            "p_remarks":        "remarks",
        }
        for src, dst in keymap.items():
            if src in incoming and dst not in incoming:
                incoming[dst] = incoming[src]

        # (optional) secure clerk id from session
        user_payload = request.session.get("user") or {}
        if user_payload.get("user_id"):
            incoming["clerk_staff_id"] = user_payload["user_id"]

        def to_int(x):
            try:
                return int(x)
            except (TypeError, ValueError):
                return None

        clerk_staff_id = to_int(incoming.get("clerk_staff_id"))
        person_id      = to_int(incoming.get("person_id"))
        request_id     = to_int(incoming.get("request_id"))
        status_id      = to_int(incoming.get("status_id"))
        remarks        = incoming.get("remarks")
        if isinstance(remarks, str) and not remarks.strip():
            remarks = None

        print("🧰 Normalized:", {
            "clerk_staff_id": clerk_staff_id,
            "person_id": person_id,
            "request_id": request_id,
            "status_id": status_id,
            "remarks": remarks
        })

        # validate
        missing = [k for k, v in {
            "clerk_staff_id": clerk_staff_id,
            "person_id":      person_id,
            "request_id":     request_id,
            "status_id":      status_id,
        }.items() if v is None]
        if missing:
            print("❌ Missing:", missing)
            return Response({"error": "Missing/invalid required fields.", "fields": missing},
                            status=status.HTTP_400_BAD_REQUEST)

        rpc_args = {
            "p_clerk_staff_id": clerk_staff_id,
            "p_person_id":      person_id,
            "p_request_id":     request_id,  # <-- this should be your verify_req_id
            "p_status_id":      status_id,   # 7 approve / 8 decline
            "p_remarks":        remarks,
        }
        print("📤 RPC Args:", rpc_args)

        try:
            rpc = supabase.rpc("approve_person_by_clerk", rpc_args).execute()
            print("📥 RPC Result:", rpc.data)
            return Response({"message": "Approval processed.", "rpc_result": rpc.data}, status=status.HTTP_200_OK)
        except Exception as e:
            err_msg = e.args[0].get("message") if getattr(e, "args", None) and isinstance(e.args[0], dict) else str(e)
            print("❌ RPC Error:", err_msg)
            return Response({"error": err_msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
