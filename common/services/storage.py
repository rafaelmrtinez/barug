# common/services/storage.py
from __future__ import annotations

from typing import Any, Dict, Optional, Union
from io import BytesIO
import mimetypes
import traceback

from django.core.files.uploadedfile import UploadedFile
from django.conf import settings

from common.supabase_client import supabase

BUCKET_DEFAULT = getattr(settings, "SUPABASE_ID_UPLOADS_BUCKET", "id-uploads")
# add other public buckets here only if you want public URLs for them
PUBLIC_BUCKETS = {BUCKET_DEFAULT}
_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png"}


def _to_bytes(obj: Union[UploadedFile, BytesIO, bytes, str]) -> bytes:
    if isinstance(obj, UploadedFile):
        try:
            obj.seek(0)
        except Exception:
            pass
        return obj.read()
    if isinstance(obj, BytesIO):
        obj.seek(0)
        return obj.read()
    if isinstance(obj, (bytes, bytearray)):
        return bytes(obj)
    if isinstance(obj, str):
        with open(obj, "rb") as f:
            return f.read()
    raise TypeError(f"Unsupported file type for upload: {type(obj)!r}")


def _as_str_url(val: Any, *, key_chain: tuple[str, ...] = ()) -> Optional[str]:
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        if key_chain:
            d = val
            for k in key_chain:
                if not isinstance(d, dict) or k not in d:
                    return None
                d = d[k]
            return d if isinstance(d, str) else None
        for chain in (
            ("data", "publicUrl"),
            ("publicUrl",),
            ("data", "signedUrl"),
            ("signedUrl",),
        ):
            d = val
            ok = True
            for k in chain:
                if not isinstance(d, dict) or k not in d:
                    ok = False
                    break
                d = d[k]
            if ok and isinstance(d, str):
                return d
    return None


def _strip_q(url: Optional[str]) -> Optional[str]:
    if not url:
        return url
    return url[:-1] if isinstance(url, str) and url.endswith("?") else url


def _guess_image_ct(path: str, data: bytes, fallback_ct: Optional[str]) -> str:
    ct, _ = mimetypes.guess_type(path)
    if ct in _ALLOWED_IMAGE_TYPES:
        return ct
    if fallback_ct in _ALLOWED_IMAGE_TYPES:
        return fallback_ct
    head = data[:16]
    if head.startswith(b"\xFF\xD8\xFF"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return "application/octet-stream"


def upload_to_storage(
    file_obj: Union[UploadedFile, BytesIO, bytes, str],
    *,
    path: str,
    bucket: Optional[str] = None,
    upsert: bool = True,
    make_public: bool = True,
    content_type: Optional[str] = None,
    reset_metadata: bool = True,
) -> Dict[str, Any]:
    """
    Upload to Supabase Storage with hardened content-type and URL handling.
    Logs key steps to the console.
    """
    bucket_name = bucket or BUCKET_DEFAULT
    print(f"[storage] upload_to_storage: bucket={bucket_name} path={path} "
          f"upsert={upsert} make_public={make_public} reset_metadata={reset_metadata}")

    data = _to_bytes(file_obj)

    uploaded_ct = getattr(file_obj, "content_type", None) if isinstance(file_obj, UploadedFile) else None
    ct = content_type or _guess_image_ct(path, data, uploaded_ct)
    print(f"[storage] content-type: requested={content_type} fallback_from_upload={uploaded_ct} final={ct} size={len(data)}B")

    # Important: delete first so any old metadata (e.g., text/plain) is wiped
    if reset_metadata:
        try:
            print(f"[storage] remove old object if exists: {bucket_name}/{path}")
            supabase.storage.from_(bucket_name).remove([path])
        except Exception as e:
            print(f"[storage] remove ignored error: {e}")

    file_options = {
        "contentType": str(ct),                     # MUST be string
        "upsert": "true" if upsert else "false",
    }

    # Upload (raises on failure)
    try:
        print(f"[storage] uploading -> {bucket_name}/{path}")
        _ = supabase.storage.from_(bucket_name).upload(path, file=data, file_options=file_options)
        print(f"[storage] upload OK -> {bucket_name}/{path}")
    except Exception:
        print("[storage] upload FAILED")
        traceback.print_exc()
        raise

    public_url: Optional[str] = None
    signed_url: Optional[str] = None

    if make_public and bucket_name in PUBLIC_BUCKETS:
        try:
            p = supabase.storage.from_(bucket_name).get_public_url(path)
            public_url = _strip_q(_as_str_url(p))
            print(f"[storage] public_url: {public_url}")
        except Exception as e:
            print(f"[storage] get_public_url error: {e}")

    if make_public and not public_url:
        try:
            s = supabase.storage.from_(bucket_name).create_signed_url(path, expires_in=60 * 60 * 24 * 365)
            signed_url = _strip_q(_as_str_url(s))
            print(f"[storage] signed_url: {signed_url}")
        except Exception as e:
            print(f"[storage] create_signed_url error: {e}")

    return {
        "bucket": bucket_name,
        "path": path,
        "public_url": public_url,
        "signed_url": signed_url,
        "uploaded": True,
        "content_type": ct,
    }
