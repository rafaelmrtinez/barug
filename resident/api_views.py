from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from supabase_client import supabase  # Your Supabase client
import jwt
from rest_framework.permissions import AllowAny

JWT_SECRET = settings.SECRET_KEY
JWT_ALGORITHM = "HS256"


class ResidentRegisterAPIView(APIView):
    """
    Resident Registration API (Online)
    """
    def post(self, request):
        try:
            data = request.data

            email = data.get('email')
            password = data.get('password')

            if not email or not password:
                return Response(
                    {"error": "Email and password are required."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # ✅ Upload file to Supabase Storage (if provided)
            file_url = None
            id_photo = request.FILES.get('id_photo')
            if id_photo:
                file_path = f"residents/{email}/{id_photo.name}"
                supabase.storage.from_("residents-photos").upload(file_path, id_photo)
                file_url = (
                    f"{settings.SUPABASE_URL}/storage/v1/object/public/residents-photos/{file_path}"
                )

            # ✅ Step 1: Call Supabase stored procedure (DB registration first)
            rpc_payload = {
                "p_added_by_id": None,  # Staff ID if applicable
                "p_barangay": data.get('barangay'),
                "p_birthdate": data.get('date_of_birth'),
                "p_city": data.get('city'),
                "p_civil_status_id": data.get('civil_status_id'),
                "p_credential_id": None,  # Auth not yet created
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
                "p_password": password,  # Raw password (hashed in DB)
                "p_person_img": file_url,
                "p_religion_id": data.get('religion_id'),
                "p_sex_id": data.get('sex_id'),
                "p_sitio_purok": data.get('purok'),
                "p_street": data.get('street'),
                "p_suffix": data.get('suffix'),
                "p_username": "temporary",  # Placeholder username
                "p_verification_status_id": None,
                "p_verified_by_id": None,
            }
            
            rpc_response = supabase.rpc("register_resident_with_verification", rpc_payload).execute()

            if not rpc_response.data:
                return Response(
                    {"error": "This email address is already in use by a registered person."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # ✅ Stored procedure returned person_code as plain string
            resident_code = rpc_response.data  # e.g., "P08-N004"

            # ✅ Fetch person_id using resident_code
            person_query = supabase.from_("person").select("person_id").eq("person_code", resident_code).single().execute()

            if not person_query.data:
                return Response(
                    {"error": "Could not find resident in database."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            person_id = person_query.data["person_id"]

            # ✅ Step 2: Supabase Auth Sign Up (after DB success)
            auth_response = supabase.auth.sign_up({
                "email": email,
                "password": password
            })

            auth_user_id = auth_response.user.id  # Supabase UUID

            # ✅ Step 3: Update person_credential with real values
            update_response = supabase.table("person_credential").update({
                "credential_id": auth_user_id,
                "username": email,  # Set username as email
            }).eq("person_id", person_id).execute()

            if update_response.data is None:
                return Response(
                    {"error": "Failed to update person credential record."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # ✅ Success
            return Response(
                {
                    "message": "Resident registered successfully.",
                    "resident_code": resident_code,
                    "id_photo_url": file_url,
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            print("Registration error:", e)
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


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