# common/services/verify_id.py
from types import SimpleNamespace
from typing import BinaryIO, Optional, Tuple
import requests
from uuid import uuid4

from django.conf import settings

from common.supabase_client import supabase

BUCKET = settings.SUPABASE_ID_UPLOADS_BUCKET


def _upload_file(file_obj: BinaryIO, content_type: str, key: str) -> str:
    """
    Uploads bytes to Supabase Storage. Returns the object path (key).
    """
    # NOTE: supabase-py wants raw bytes
    data = file_obj.read()
    supabase.storage.from_(BUCKET).upload(
        key,
        data,
        {"content-type": content_type},
    )
    return key


def _public_url(path: str) -> str:
    # If the bucket is public, you can build the public URL like this:
    return f"{settings.SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{path}"


def verify_id_via_edge(
    *,
    supabase_uid: str,         # same "personId" your RN code uses for storage path
    profile_name: str,
    id_type_code: str,         # normalized, e.g. "ephil_id"
    front_path: str,
    back_path: str,
    selfie_path: str,
    timeout: int = 60,
) -> SimpleNamespace:
    """
    Calls the Supabase Edge Function verify-id and returns a SimpleNamespace:
      ok: bool (PASSED -> True)
      status: 'PASSED' | 'FAILED'
      data: dict (raw payload from EF)
    """
    url = f"{settings.SUPABASE_URL}/functions/v1/verify-id"
    headers = {
        # Use service role on the server:
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "person_id": supabase_uid,
        "id_type": id_type_code,
        "front_path": front_path,
        "back_path": back_path,
        "selfie_path": selfie_path,
        "profile_name": profile_name,
    }

    r = requests.post(url, json=body, headers=headers, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    status = str(data.get("status", "")).upper()
    return SimpleNamespace(ok=(status == "PASSED"), status=status, data=data)
