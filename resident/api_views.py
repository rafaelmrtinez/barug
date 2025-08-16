from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.parsers import JSONParser
from dependency_injector.wiring import inject, Provide
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator
from rest_framework import status
from django.conf import settings
from src.infra.authentication.claims import Claims
from barug.utils.rate_limiter import CustomRateLimiter
from resident.serializers.membership import MembershipSerializer
from barug.constants import INTERNAL_ERROR
from src.app.bootstrap.app_containers import AppContainer
from src.core.contracts.app.family_service import IFamilyMembershipService
from src.core.exceptions.domain_exceptions import DomainException
from src.infra.exceptions.supabase_sdk.family_member_exist import FamilyMemberAlreadyExistException
from src.infra.exceptions.supabase_sdk.foreign_key import ForeignKeyException
from src.infra.exceptions.supabase_sdk.missing_response import MissingResponseException
from src.infra.exceptions.supabase_sdk.pending_join_family_request import PendingFamilyRequestException
from supabase_client import supabase  # Your Supabase client
import jwt
from rest_framework.permissions import AllowAny
import requests
from authentication.utils.email_helpers import send_signup_confirmation_link
from authentication.utils.supabase_auth import delete_supabase_user

JWT_SECRET = settings.SECRET_KEY
JWT_ALGORITHM = "HS256"


class FamilyMembership(APIView):
    """
        Description:
            API View for handling the process of joining a family unit.
            
        Request Data Types:
            - resident_id (int): Unique identifier of the resident.
            - household_id (int): Unique identifier of the household.
            - family_id (int): Unique identifier of the family.
            - household_head_relationship (int): Relationship of the resident to the household head.
            - family_head_relationship (int): Relationship of the resident to the family head.

        Note:
            - Only JSON request bodies are accepted. Ensure the request header includes:
            "Content-Type: application/json".
            - JWT authentication is required. Include the token in requests made via fetch API,
            Axios, or other HTTP clients. Requests without authentication will be rejected.

        Example Request:
            {
                "household_id": 1,
                "family_id": 1,
                "household_head_relationship": 1,
                "family_head_relationship": 1
            }

        Returns:
            - HTTP 200 OK on success.
    """

    parser_classes = [JSONParser]
    
    @method_decorator(ratelimit(key='user_or_ip', rate='10/s', block=False))
    @inject
    def post(self, request: Request, service: IFamilyMembershipService = Provide[AppContainer.family_membership]) -> Response:
        if CustomRateLimiter.is_ratelimited(request=request):
            return Response({"error": "Rate limit exceeded. Please try again later."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        user = Claims.verify_jwt_token(request.headers.get("Authorization"))
        if not user:
            return Response({"error": "Unauthorized Access."}, status=status.HTTP_401_UNAUTHORIZED)
        serializer = MembershipSerializer(
            data={
                **request.data,
                "resident_id": user["user_id"],
                "username": user["username"],
                "role": user["role"]
            })
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        validated_data = serializer.validated_data
        is_success: bool = service.execute(
                resident_id=validated_data["resident_id"],
                household_id=validated_data["household_id"],
                family_id=validated_data["family_id"],
                household_head_relationship=validated_data["household_head_relationship"],
                family_head_relationship=validated_data["family_head_relationship"],
            )
        if not is_success:
            return Response({"error": "Unable to join family at the moment."}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(status=status.HTTP_200_OK)

class ResidentRegisterAPIView(APIView):
    def post(self, request):
        try:
            data = request.data
            email = data.get('email')
            password = data.get('password')

            if not email or not password:
                return Response({"error": "Email and password are required."},
                                status=status.HTTP_400_BAD_REQUEST)

            # ✅ Step 1: Supabase Admin API user creation (no confirmation)
            # [DEBUG] print(f"🚀 Creating Supabase user via Admin API for {email}")
            user_create_response = requests.post(
                f"{settings.SUPABASE_URL}/auth/v1/admin/users",
                headers={
                    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}"
                },
                json={
                    "email": email,
                    "password": password,
                    "email_confirm": False
                }
            )

            if user_create_response.status_code != 200:
                # [DEBUG] print("❌ Supabase Admin API user creation failed.")
                return Response({
                    "error": "Failed to create user in Supabase Auth.",
                    "response": user_create_response.text
                }, status=status.HTTP_400_BAD_REQUEST)

            auth_data = user_create_response.json()
            auth_user_id = auth_data["id"]
            # [DEBUG] print(f"✅ Supabase user created: {auth_user_id}")

            # ✅ Step 2: Upload ID photo (optional)
            file_url = None
            id_photo = request.FILES.get('id_photo')
            if id_photo:
                file_path = f"residents/{email}/{id_photo.name}"
                supabase.storage.from_("residents-photos").upload(file_path, id_photo)
                file_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/residents-photos/{file_path}"
                # [DEBUG] print(f"📸 ID photo uploaded: {file_url}")

            # ✅ Step 3: Call stored procedure
            rpc_payload = {
                "p_added_by_id": None,
                "p_barangay": data.get('barangay'),
                "p_birthdate": data.get('date_of_birth'),
                "p_city": data.get('city'),
                "p_civil_status_id": data.get('civil_status_id'),
                "p_credential_id": auth_user_id,
                "p_doc_file_path": None,
                "p_doc_type_id": data.get('id_type_id'),
                "p_education_id": data.get('education_level_id'),
                "p_email": email,
                "p_employment_status_id": data.get('employment_status_id'),
                "p_first_name": data.get('first_name'),
                "p_gov_mem_prog_id": None,
                "p_is_business_owner": False,
                "p_is_email_verified": False,
                "p_last_name": data.get('last_name'),
                "p_middle_name": data.get('middle_name'),
                "p_mnthly_personal_income_id": None,
                "p_mobile_num": data.get('mobile_number'),
                "p_nationality_id": data.get('nationality_id'),
                "p_occupation_id": data.get('occupation_id'),
                "p_password": password,
                "p_person_img": file_url,
                "p_religion_id": data.get('religion_id'),
                "p_sex_id": data.get('sex_id'),
                "p_sitio_purok": data.get('purok'),
                "p_street": data.get('street'),
                "p_suffix": data.get('suffix'),
                "p_username": email,
                "p_verification_status_id": None,
                "p_verified_by_id": None,
            }

            # [DEBUG] print("📦 Calling stored procedure register_resident_with_verification...")
            rpc = supabase.rpc("register_resident_with_verification", rpc_payload).execute()

            # ❌ Stored procedure error
            if hasattr(rpc, "error") and rpc.error is not None:
                # [DEBUG] print("❌ Stored procedure error:", rpc.error)
                delete_supabase_user(auth_user_id)
                return Response({
                    "error": rpc.error.get("message", "Registration failed."),
                    "code": rpc.error.get("code")
                }, status=status.HTTP_400_BAD_REQUEST)

            if not rpc.data:
                # [DEBUG] print("❌ Stored procedure returned no data.")
                delete_supabase_user(auth_user_id)
                return Response({
                    "error": "Registration failed due to empty result."
                }, status=status.HTTP_400_BAD_REQUEST)

            # ✅ Step 4: Get person_id
            resident_code = rpc.data
            # [DEBUG] print(f"✅ Resident registered with code: {resident_code}")
            person_query = supabase.from_("person").select("person_id").eq("person_code", resident_code).single().execute()

            if not person_query.data:
                # [DEBUG] print("❌ Could not find person after registration.")
                delete_supabase_user(auth_user_id)
                return Response({
                    "error": "Could not find resident in database."
                }, status=status.HTTP_400_BAD_REQUEST)

            person_id = person_query.data["person_id"]

            # ✅ Step 5: Update person_credential
            update_response = supabase.table("person_credential").update({
                "credential_id": auth_user_id,
                "username": email
            }).eq("person_id", person_id).execute()

            if update_response.data is None:
                # [DEBUG] print("❌ Failed to update person_credential.")
                delete_supabase_user(auth_user_id)
                return Response({
                    "error": "Failed to update credentials."
                }, status=status.HTTP_400_BAD_REQUEST)

            # ✅ Step 6: Send confirmation email only after success
            # [DEBUG] print(f"📬 Sending confirmation email for user: {auth_user_id}")
            send_signup_confirmation_link(email)

            # [DEBUG] print("✅ Registration complete.")
            return Response({
                "message": "Resident registered successfully.",
                "resident_code": resident_code,
                "id_photo_url": file_url,
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            # [DEBUG] print("🔥 Registration error:", e)
            auth_user_id = locals().get("auth_user_id", None)
            if auth_user_id:
                delete_supabase_user(auth_user_id)

            return Response({
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ResidentProfileAPIView(APIView):
    """
    Fetch full resident profile for logged-in user
    """

    authentication_classes = []  # 👈 disable DRF auth
    permission_classes = []      # 👈 disable DRF auth

    def get(self, request):
        # ✅ Read token from header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return Response(
                {"error": "Authorization header missing or invalid."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        token = auth_header.split(" ")[1]

        try:
            # ✅ Decode your custom JWT
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = payload.get("user_id")
            if not user_id:
                return Response({"error": "Invalid token: no user_id."}, status=400)

            # ✅ Call Supabase to fetch profile
            profile_resp = supabase.rpc("get_specific_resident_full_profile", {
                "p_person_id": user_id
            }).execute()

            if not profile_resp.data:
                return Response({"error": "Resident profile not found."}, status=404)

            return Response(profile_resp.data[0], status=200)

        except jwt.ExpiredSignatureError:
            return Response({"error": "Token expired."}, status=401)
        except jwt.InvalidTokenError:
            return Response({"error": "Invalid token."}, status=401)