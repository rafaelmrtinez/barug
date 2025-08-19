# resident/api_views.py
# resident/api_views.py
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.parsers import JSONParser
from dependency_injector.wiring import inject, Provide
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator
from rest_framework import status
from django.conf import settings
from resident.serializers.family_selection import FamilySelectionSerializer
from resident.serializers.membership_search import MembershipSearch
from src.core.contracts.app.service import IService

from src.infra.authentication.claims import Claims
from barug.utils.rate_limiter import CustomRateLimiter
from resident.serializers.membership import MembershipSerializer
from barug.constants import INTERNAL_ERROR
from src.app.bootstrap.app_containers import AppContainer
from src.core.contracts.app.family_service import IFamilyMembershipService
from src.core.exceptions.domain_exceptions import DomainException

from datetime import datetime, date
from rest_framework.permissions import IsAuthenticated, AllowAny

from supabase_client import supabase  # Your Supabase client
# import jwt
from rest_framework.permissions import AllowAny
import requests
from barug.constants import RESOURCE_ACCESS_DENIED
from authentication.utils.email_helpers import send_signup_confirmation_link
from authentication.utils.supabase_auth import delete_supabase_user

from resident.verification.ocr_utils import validate_doc_from_images
from resident.verification.constants import DOC_TYPE_KEY_BY_ID
from PIL import Image, UnidentifiedImageError
import os, uuid, tempfile, logging
from rest_framework.parsers import MultiPartParser, FormParser
import re

logger = logging.getLogger(__name__)

# JWT_SECRET = settings.SECRET_KEY
# JWT_ALGORITHM = "HS256"



# ---------- NEW: helpers for username pattern ----------
_USERNAME_SUFFIX_DOMAIN = "@user"

def _slug_module(s: str | None) -> str:
    if s is None:
        return ""
    return re.sub(r'[^a-z0-9]+', '', str(s).strip().lower())

def _mmddyy_from_input(dob_raw) -> str | None:
    """Return MMDDYY from various DOB input formats, or None if invalid."""
    if not dob_raw:
        return None
    dt = None
    if isinstance(dob_raw, datetime):
        dt = dob_raw.date()
    elif isinstance(dob_raw, date):
        dt = dob_raw
    else:
        val = str(dob_raw).strip()
        # Try common formats
        fmts = [
            "%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d",
            "%d-%m-%Y", "%d/%m/%Y",
            "%m/%d/%y", "%m-%d-%y", "%d-%m-%y", "%d/%m/%y",
            "%Y%m%d", "%m%d%Y"
        ]
        for f in fmts:
            try:
                dt = datetime.strptime(val, f).date()
                break
            except ValueError:
                continue
        if dt is None:
            # Last ditch: extract digits and try YYYY-MM-DD ordering
            digits = re.sub(r"\D+", "", val)
            try:
                if len(digits) == 8:
                    # Heuristic: try YYYYMMDD first, else MMDDYYYY
                    try:
                        dt = datetime.strptime(digits, "%Y%m%d").date()
                    except ValueError:
                        dt = datetime.strptime(digits, "%m%d%Y").date()
            except Exception:
                dt = None
    return dt.strftime("%m%d%y") if dt else None

def generate_username(last_name: str | None, dob_raw) -> str:
    """
    Always produce: lastname.MMDDYY@user
    Fallbacks:
      - If last_name missing -> "user.MMDDYY@user" or "user.000000@user"
      - If DOB invalid/missing -> use "000000" for date code
    """
    ln = _slug_module(last_name) or "user"
    mmddyy = _mmddyy_from_input(dob_raw) or "000000"
    return f"{ln}.{mmddyy}{_USERNAME_SUFFIX_DOMAIN}"[:150]
# ------------------------------------------------------


class ResidentRegisterBHWAPIView(APIView):
    permission_classes = [AllowAny]
    parser_classes = (MultiPartParser, FormParser)

    PHOTOS_BUCKET = "residents-photos"
    DOCS_BUCKET = "residents-docs"

    # ---------- helpers ----------
    @staticmethod
    def _to_int(v):
        try:
            return int(v) if v not in (None, "", "null") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_bool(v, default=False):
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in {"1", "true", "t", "yes", "y", "on"}
        return default

    @staticmethod
    def _is_image(uploaded_file) -> bool:
        try:
            uploaded_file.seek(0)
            Image.open(uploaded_file).verify()
            uploaded_file.seek(0)
            return True
        except (UnidentifiedImageError, OSError):
            try:
                uploaded_file.seek(0)
            except Exception:
                pass
            return False

    @staticmethod
    def _scalar(x):
        if isinstance(x, (list, tuple, set)):
            for i in x:
                if i not in (None, ''):
                    return str(i)
            return ''
        return '' if x is None else str(x)

    @staticmethod
    def _slug(s: str) -> str:
        return re.sub(r'[^a-z0-9]+', '', s.strip().lower())

    @staticmethod
    def _storage_base(auth_user_id: str | None, email: str | None) -> str:
        if auth_user_id:
            return f"residents/{auth_user_id}"
        if email:
            return f"residents/{email}"
        return f"residents/walkins/{uuid.uuid4().hex}"

    def _upload(self, bucket: str, file_obj, path_prefix: str) -> str | None:
        if not file_obj:
            return None

        # read bytes
        try:
            try: file_obj.seek(0)
            except Exception: pass
            data = file_obj.read()
            try: file_obj.seek(0)
            except Exception: pass
        except Exception as e:
            logger.exception("Failed reading upload bytes: %s", e)
            return None

        if not data:
            logger.warning("Upload skipped: no bytes read for %s", getattr(file_obj, "name", "unknown"))
            return None

        import os, uuid, mimetypes
        orig = getattr(file_obj, "name", "file")
        ext = os.path.splitext(orig)[1] or ".jpg"
        key = f"{path_prefix.strip('/')}/{uuid.uuid4().hex}{ext}"

        # pick a sensible content type
        ct = getattr(file_obj, "content_type", None) or mimetypes.guess_type(orig)[0] or "image/jpeg"

        try:
            res = supabase.storage.from_(bucket).upload(
                key,
                data,
                file_options={"content_type": ct},  # <-- string, no 'upsert'
            )
            if getattr(res, "error", None):
                logger.error("Supabase upload error: %s", res.error)
                return None

            # If the bucket is public, this URL will work directly
            return f"{settings.SUPABASE_URL}/storage/v1/object/public/{bucket}/{key}"
        except Exception as e:
            logger.exception("Supabase upload exception for %s: %s", key, e)
            return None


    # ---------- main ----------
    def post(self, request):
        auth_user_id = None
        try:
            d = request.data
            email = (d.get("email") or "").strip() or None
            password = d.get("password")  # only required if email exists

            # (1) Optional Auth: only when email is provided
            if email:
                if not password:
                    return Response({"error": "Password is required when email is provided."}, status=400)

                user_create_response = requests.post(
                    f"{settings.SUPABASE_URL}/auth/v1/admin/users",
                    headers={
                        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
                    },
                    json={
                        "email": email,
                        "password": password,
                        "email_confirm": False,
                        "user_metadata": {"source": "bhw_register", "placeholder_email": False},
                    },
                    timeout=20,
                )
                if user_create_response.status_code != 200:
                    return Response(
                        {"error": "Failed to create user in Supabase Auth.", "response": user_create_response.text},
                        status=400,
                    )
                auth_user_id = user_create_response.json()["id"]
            else:
                # No-email path: NO auth signup, password can be ignored
                password = d.get("password")

            # Files from request (may be None)
            person_img = request.FILES.get("person_img")
            front_file = request.FILES.get("front_doc")
            back_file  = request.FILES.get("back_doc")
            selfie_file = request.FILES.get("selfie")

            # (2) OCR if front/back provided
            if front_file or back_file:
                raw_doc_type_id = d.get("id_type_id") or d.get("document_type_id")
                try:
                    doc_type_id = int(raw_doc_type_id) if raw_doc_type_id not in (None, "", "null") else None
                except (TypeError, ValueError):
                    doc_type_id = None

                if not doc_type_id:
                    if auth_user_id:
                        delete_supabase_user(auth_user_id)
                    return Response({"error": "id_type_id is required when uploading ID images."}, status=400)

                if not front_file:
                    if auth_user_id:
                        delete_supabase_user(auth_user_id)
                    return Response({"error": "front_doc is required for ID verification."}, status=400)

                if not self._is_image(front_file):
                    if auth_user_id:
                        delete_supabase_user(auth_user_id)
                    return Response({"error": "front_doc must be a valid image."}, status=400)
                if back_file and not self._is_image(back_file):
                    if auth_user_id:
                        delete_supabase_user(auth_user_id)
                    return Response({"error": "back_doc must be a valid image."}, status=400)

                doc_type_key = DOC_TYPE_KEY_BY_ID.get(doc_type_id)
                if not doc_type_key:
                    if auth_user_id:
                        delete_supabase_user(auth_user_id)
                    return Response({"error": "Unknown doc_type_id."}, status=400)

                name_tuple = (
                    d.get("first_name", "") or "",
                    d.get("last_name", "") or "",
                    d.get("middle_name", "") or "",
                )

                ocr = validate_doc_from_images(front_file, back_file, doc_type_key, name_tuple)

                # Debug (optional)
                print("\n===== 🛠 BHW OCR DEBUG =====")
                print(f"Doc Type Key: {doc_type_key}")
                print(f"doc_type_ok: {ocr.get('doc_type_ok')}")
                print(f"name_ok: {ocr.get('name_ok')}  hits: {ocr.get('name_hits')}")
                print(f"Final OK: {ocr.get('ok')}  reason: {ocr.get('reason')}")
                print(f"Matched Side: {ocr.get('which_matched')}")
                print("============================\n")

                if not ocr.get("ok"):
                    if auth_user_id:
                        delete_supabase_user(auth_user_id)
                    return Response(
                        {
                            "error": "OCR validation failed.",
                            "doc_type_ok": ocr.get("doc_type_ok"),
                            "name_ok": ocr.get("name_ok"),
                            "reason": ocr.get("reason") or "ID text did not match expected document or name.",
                        },
                        status=400,
                    )

                # Rewind files before upload (OCR/read may have moved the cursor)
                try:
                    if front_file: front_file.seek(0)
                    if back_file: back_file.seek(0)
                    if selfie_file: selfie_file.seek(0)
                    if person_img: person_img.seek(0)
                except Exception:
                    pass

            # If no explicit person_img, reuse selfie (optional)
            if not person_img and selfie_file:
                person_img = selfie_file

            # (3) Diagnostics (optional but helpful)
            for k, f in {
                "person_img": person_img,
                "front_doc": front_file,
                "back_doc": back_file,
                "selfie": selfie_file
            }.items():
                if f:
                    logger.info(
                        "FILES[%s]: name=%s size=%s ct=%s",
                        k, getattr(f, "name", None), getattr(f, "size", None), getattr(f, "content_type", None)
                    )
                else:
                    logger.warning("FILES[%s]: missing", k)

            # ---------- NEW: ALWAYS compute username as lastname.MMDDYY@user ----------
            username = generate_username(d.get('last_name'), d.get('date_of_birth'))

            # (4) Upload after OCR passes (or if no OCR needed)
            base = self._storage_base(auth_user_id, email)
            person_img_url = self._upload(self.PHOTOS_BUCKET, person_img, base)
            front_doc_url  = self._upload(self.DOCS_BUCKET,   front_file,  f"{base}/docs")
            back_doc_url   = self._upload(self.DOCS_BUCKET,   back_file,   f"{base}/docs")
            selfie_url     = self._upload(self.DOCS_BUCKET,   selfie_file, f"{base}/docs")

            occ = d.get("occupation")
            # (5) RPC payload
            rpc_payload = {
                # core identity
                "p_last_name": d.get("last_name"),
                "p_first_name": d.get("first_name"),
                "p_middle_name": d.get("middle_name"),
                "p_suffix": d.get("suffix"),

                # demographics/contact
                "p_birthdate": d.get("date_of_birth"),
                "p_email": email,  # may be None
                "p_mobile_num": d.get("mobile_number"),
                "p_sex_id": self._to_int(d.get("sex_id")),
                "p_civil_status_id": self._to_int(d.get("civil_status_id")),
                "p_nationality_id": self._to_int(d.get("nationality_id")),
                "p_religion_id": self._to_int(d.get("religion_id")),

                # address
                "p_city": d.get("city"),
                "p_barangay": d.get("barangay"),
                "p_sitio_purok": d.get("purok"),
                "p_street": d.get("street"),

                # auth linkage
                "p_credential_id": auth_user_id,  # None if no email
                "p_username": username,           # <-- NEW: use formatted username
                "p_password": password,           # None if no email

                # meta
                "p_added_by_id": self._to_int(d.get("added_by_id")),
                "p_is_email_verified": False,
                "p_is_business_owner": self._to_bool(d.get("is_business_owner"), default=False),

                # media & docs
                "p_person_img": person_img_url,
                "p_front_doc_path": front_doc_url,
                "p_back_doc_path": back_doc_url,
                "p_doc_type_id": self._to_int(d.get("id_type_id") or d.get("document_type_id")),
                "p_selfie_path": selfie_url,

                # verification
                "p_verification_status_id": 2,

                # socioeconomic
                "p_education_id": self._to_int(d.get("education_level_id")),
                "p_employment_status_id": self._to_int(d.get("employment_status_id")),
                "p_occupation": occ,
                "p_gov_mem_prog_id": self._to_int(d.get("gov_mem_prog_id") or d.get("gov_prog_id")),
                "p_mnthly_personal_income_id": self._to_int(d.get("mnthly_personal_income_id") or d.get("monthly_personal_income_id")),

                # channel flag
                "is_bhw_registration": self._to_bool(d.get("is_bhw_registration"), default=False),
            }

            print(
                str(rpc_payload)
                .replace(", ", ",\n ")
                .replace("{", "{\n", 1)
                .rsplit("}", 1)[0] + "\n}"
            )

            rpc = supabase.rpc("register_resident_with_verification", rpc_payload).execute()

            if getattr(rpc, "error", None):
                if auth_user_id:
                    delete_supabase_user(auth_user_id)
                return Response(
                    {"error": rpc.error.get("message", "Registration failed."), "code": rpc.error.get("code")},
                    status=400,
                )

            if not getattr(rpc, "data", None):
                if auth_user_id:
                    delete_supabase_user(auth_user_id)
                return Response({"error": "Registration failed due to empty result."}, status=400)

            resident_code = rpc.data

            # (6) Bind credentials row
            person_q = supabase.from_("person").select("person_id").eq("person_code", resident_code).single().execute()
            if not person_q.data:
                if auth_user_id:
                    delete_supabase_user(auth_user_id)
                return Response({"error": "Could not find resident in database."}, status=400)

            person_id = person_q.data["person_id"]

            update_body = {"username": username}  # <-- NEW: always our pattern
            if auth_user_id:
                update_body["credential_id"] = auth_user_id

            upd = supabase.table("person_credential").update(update_body).eq("person_id", person_id).execute()
            if upd.data is None:
                if auth_user_id:
                    delete_supabase_user(auth_user_id)
                return Response({"error": "Failed to update credentials."}, status=400)

            # (7) Email confirmation only when email exists
            if email:
                send_signup_confirmation_link(email)

            return Response(
                {
                    "message": "Resident registered successfully.",
                    "resident_code": resident_code,
                    "p_person_img": person_img_url,
                    "front_doc_url": front_doc_url,
                    "back_doc_url": back_doc_url,
                    "selfie_url": selfie_url,
                    "username": username,  # <-- NEW: return it for clarity
                },
                status=201,
            )

        except Exception as e:
            if auth_user_id:
                delete_supabase_user(auth_user_id)
            return Response({"error": str(e)}, status=500)




class FamilyUnitSelection(APIView):
    
    parser_classes = [JSONParser]
    
    @method_decorator(ratelimit(key='user_or_ip', rate='5/s', block=False))
    @inject
    def get(self, request: Request, service: IService = Provide[AppContainer.family_selection]) -> Response:
        if CustomRateLimiter.is_ratelimited(request=request):
            return Response({"error": "Rate limit exceeded. Please try again later."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        user = Claims.verify_jwt_token(request.headers.get("Authorization"))
        if not user:
            return Response({"error": RESOURCE_ACCESS_DENIED}, status=status.HTTP_401_UNAUTHORIZED)
        household_id = request.query_params.get("q", None)
        serializer = FamilySelectionSerializer(data={
                'household_id': household_id,
                "resident_id": user["user_id"],
                "username": user["username"],
                "role": user["role"]
            })
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        result = service.execute(household_id=serializer.validated_data['household_id'])
        if not result:
            return Response({'message': 'No results found'},status=status.HTTP_200_OK)
        return Response({'message': result}, status=status.HTTP_200_OK)


class HouseholdMembershipSearch(APIView):
    """
    API View for searching household memberships.
    """
    parser_classes = [JSONParser]
    
    @method_decorator(ratelimit(key='user_or_ip', rate='10/s', block=False))
    @inject
    def get(self, request: Request, service: IService = Provide[AppContainer.household_search_service]) -> Response:
        if CustomRateLimiter.is_ratelimited(request=request):
            return Response({"error": "Rate limit exceeded. Please try again later."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        user = Claims.verify_jwt_token(request.headers.get("Authorization"))
        if not user:
            return Response({"error": RESOURCE_ACCESS_DENIED}, status=status.HTTP_401_UNAUTHORIZED)
        key = request.query_params.get("q", None)
        serializer = MembershipSearch(data={
                'key': key,
                "resident_id": user["user_id"],
                "username": user["username"],
                "role": user["role"]
            })
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        result = service.execute(key=key)
        if not result:
            return Response({'message': 'No results found'},status=status.HTTP_200_OK)
        return Response({'message': result}, status=status.HTTP_200_OK)


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
                "p_added_by_id": None if not data.get('added_by_id') else int(data.get('added_by_id')),
                "p_added_by_id": None if not data.get('added_by_id') else int(data.get('added_by_id')),
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
    permission_classes = [IsAuthenticated]  # use DRF auth (header or cookie)

    def get(self, request):
        user_id = request.user.uid  # comes from token claims

        profile_resp = supabase.rpc("get_specific_resident_full_profile", {
            "p_person_id": user_id
        }).execute()

        # print(profile_resp.data)
        if not profile_resp.data:
            return Response({"error": "Resident profile not found."}, status=404)

        return Response(profile_resp.data[0], status=200)


class PersonVerificationRequestAPIView(APIView):
    """
    Accept socioeconomic fields + required ID images when doc_type_id is provided.
    Use OCR to validate doc type + resident name before uploading & calling RPC.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)
    BUCKET = "residents-photos"

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

            # ✅ Default to the authenticated user
            requester_id = d.get("requester_id") or request.user.uid
            
            if not requester_id:
                return Response({"error": "Missing requester_id."}, status=status.HTTP_400_BAD_REQUEST)
            
            # if not requester_id:
            #     auth_header = request.headers.get("Authorization", "")
            #     if auth_header.startswith("Bearer "):
            #         token = auth_header.split(" ", 1)[1]
            #         try:
            #             payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            #             requester_id = payload.get("user_id")
            #         except jwt.ExpiredSignatureError:
            #             return Response({"error": "Token expired."}, status=status.HTTP_401_UNAUTHORIZED)
            #         except jwt.InvalidTokenError:
            #             return Response({"error": "Invalid token."}, status=status.HTTP_401_UNAUTHORIZED)

            # if not requester_id:
            #     return Response({"error": "Missing requester_id."}, status=status.HTTP_400_BAD_REQUEST)

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


