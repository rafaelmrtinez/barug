from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from supabase_client import supabase  # Your Supabase client
import jwt
from rest_framework.permissions import AllowAny
import requests
from authentication.utils.email_helpers import send_signup_confirmation_link
from authentication.utils.supabase_auth import delete_supabase_user

<<<<<<< HEAD
from resident.verification.ocr_utils import validate_doc_from_images
from PIL import Image, UnidentifiedImageError

# verification/constants.py

# Map your doc_type_id (from DB) to the internal OCR key.
# Make sure these IDs match your lookup table.
DOC_TYPE_KEY_BY_ID = {
    1:  "philippine_passport",
    2:  "philippine_national_id",
    3:  "sss_umid",
    4:  "gsis_ecard",
    5:  "prc_id",

    6:  "drivers_license",
    7:  "philhealth_id",
    8:  "voters_id",
    9:  "postal_id",
    10: "barangay_certificate",
    11: "senior_citizen_id",
    12: "pwd_id",
    13: "owwa_id",
    14: "ibp_id",
    15: "tin_id",
}


JWT_SECRET = settings.SECRET_KEY
JWT_ALGORITHM = "HS256"

import os, uuid, tempfile
from rest_framework.parsers import MultiPartParser, FormParser
=======
JWT_SECRET = settings.SECRET_KEY
JWT_ALGORITHM = "HS256"

>>>>>>> b910daa1f305ba4e34ee46579bd1c7883f32bbb9

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
<<<<<<< HEAD
            return Response({"error": "Invalid token."}, status=401)


class PersonVerificationRequestAPIView(APIView):
    """
    Accept socioeconomic fields + required ID images when doc_type_id is provided.
    Use OCR to validate doc type + resident name before uploading & calling RPC.
    """
    permission_classes = [AllowAny]
    parser_classes = (MultiPartParser, FormParser)
    BUCKET = "residents-photos"  # ensure bucket exists & is public

    def _upload_bytes(self, bytes_data: bytes, path: str, content_type: str):
        supabase.storage.from_(self.BUCKET).upload(
            path,
            bytes_data,
            file_options={"content-type": content_type},
        )

    def _upload_or_none(self, request, field_name: str):
        f = request.FILES.get(field_name)
        if not f:
            return None

        ext = os.path.splitext(f.name)[1] or ".jpg"
        path = f"verifications/{uuid.uuid4()}/{field_name}-{uuid.uuid4()}{ext}"
        public_base = f"{settings.SUPABASE_URL}/storage/v1/object/public/{self.BUCKET}"
        content_type = getattr(f, "content_type", None) or "application/octet-stream"

        f.seek(0)
        file_bytes = f.read()

        try:
            self._upload_bytes(file_bytes, path, content_type)
        except TypeError:
            # older SDK path fallback
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            try:
                supabase.storage.from_(self.BUCKET).upload(
                    path, tmp_path, file_options={"content-type": content_type}
                )
            finally:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

        return f"{public_base}/{path}"

    @staticmethod
    def _is_image(uploaded_file) -> bool:
        try:
            uploaded_file.seek(0)
            Image.open(uploaded_file).verify()  # quick integrity check
            uploaded_file.seek(0)
            return True
        except (UnidentifiedImageError, OSError):
            return False

    def post(self, request):
        try:
            d = request.data

            # Resolve requester_id from body, then try JWT as fallback
            requester_id = d.get("requester_id")
            if not requester_id:
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    token = auth_header.split(" ", 1)[1]
                    try:
                        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                        requester_id = payload.get("user_id")
                    except jwt.ExpiredSignatureError:
                        return Response({"error": "Token expired."}, status=status.HTTP_401_UNAUTHORIZED)
                    except jwt.InvalidTokenError:
                        return Response({"error": "Invalid token."}, status=status.HTTP_401_UNAUTHORIZED)

            if not requester_id:
                return Response({"error": "Missing requester_id."}, status=status.HTTP_400_BAD_REQUEST)

            # Required non-image fields
            required_keys = [
                "education_id",
                "employment_status_id",
                "occupation",
                "gov_mem_prog_id",
                "mnthly_personal_income_id",
                "doc_type_id",
            ]
            missing = [k for k in required_keys if not str(d.get(k, "")).strip()]
            if missing:
                return Response({"error": "Missing required fields.", "missing": missing}, status=400)

            # Map doc_type_id -> key
            try:
                doc_type_id = int(d["doc_type_id"])
            except (TypeError, ValueError):
                return Response({"error": "doc_type_id must be an integer."}, status=400)

            doc_type_key = DOC_TYPE_KEY_BY_ID.get(doc_type_id)
            if not doc_type_key:
                return Response({"error": "Unknown doc_type_id."}, status=400)

            # Files
            front_file = request.FILES.get("id_front")
            back_file  = request.FILES.get("id_back")
            selfie_file = request.FILES.get("id_selfie")

            if not front_file:
                return Response({"error": "id_front is required for ID verification."}, status=400)

            # Image validation
            if not self._is_image(front_file):
                return Response({"error": "id_front must be a valid image."}, status=400)
            if back_file and not self._is_image(back_file):
                return Response({"error": "id_back must be a valid image."}, status=400)
            if selfie_file and not self._is_image(selfie_file):
                return Response({"error": "id_selfie must be a valid image."}, status=400)

            # OCR validation
            ocr = validate_doc_from_images(
                front_file,
                back_file,
                doc_type_key,
                (d.get("first_name", ""), d.get("last_name", ""), d.get("middle_name", "")),
            )

            # 🔍 DEBUG LOGS FOR OCR
            print("\n===== 🛠 OCR DEBUG =====")
            print(f"Doc Type Key: {doc_type_key}")
            print(f"doc_type_ok: {ocr.get('doc_type_ok')}")
            print(f"name_ok: {ocr.get('name_ok')}   hits: {ocr.get('name_hits')}")
            print(f"Final OK: {ocr.get('ok')}")
            print(f"Reason: {ocr.get('reason')}")
            print(f"OCR Which Side Matched: {ocr.get('which_matched')}")
            print("---- FRONT TEXT ----")
            print(ocr.get("text_front"))
            print("---- BACK TEXT ----")
            print(ocr.get("text_back"))
            print("======================\n")

            if not ocr.get("ok"):
                return Response(
                    {
                        "error": "OCR validation failed.",
                        "doc_type_ok": ocr.get("doc_type_ok"),
                        "name_ok": ocr.get("name_ok"),
                        "reason": ocr.get("reason") or "ID text did not match expected document or name.",
                        "debug_text_front": ocr.get("text_front"),  # Optional: return to client
                        "debug_text_back": ocr.get("text_back"),
                    },
                    status=400,
                )

            # Only upload AFTER OCR passes
            front_url  = self._upload_or_none(request, "id_front")
            back_url   = self._upload_or_none(request, "id_back")
            selfie_url = self._upload_or_none(request, "id_selfie")

            # Build RPC payload
            rpc_payload = {
                "p_requester_id":               int(requester_id),
                "p_education_id":               int(d["education_id"]),
                "p_employment_status_id":       int(d["employment_status_id"]),
                "p_occupation":                 d["occupation"],
                "p_gov_mem_prog_id":            int(d["gov_mem_prog_id"]),
                "p_mnthly_personal_income_id":  int(d["mnthly_personal_income_id"]),
                "p_front_doc_path":             front_url,
                "p_back_doc_path":              back_url,
                "p_doc_type_id":                doc_type_id,
                "p_selfie_path":                selfie_url,
            }

            print("📦 RPC Payload:", rpc_payload)
            rpc = supabase.rpc("request_person_verification", rpc_payload).execute()

            if getattr(rpc, "error", None):
                return Response(
                    {"error": rpc.error.get("message"), "code": rpc.error.get("code")},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return Response({"ok": bool(rpc.data), "result": rpc.data}, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
=======
            return Response({"error": "Invalid token."}, status=401)
>>>>>>> b910daa1f305ba4e34ee46579bd1c7883f32bbb9
