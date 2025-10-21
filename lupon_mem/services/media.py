# lupon_mem/services/media.py
from __future__ import annotations
from typing import List, Dict, Any
from django.db import connection
from django.conf import settings
from supabase import create_client


def _list_mediation_photos(case_id: int, submission_id: int | None):
    """
    Return dicts the template can render. We avoid selecting a PK column
    because your environments disagree on its name ('id' vs 'media_id' vs none).
    """
    rows = []
    with connection.cursor() as cur:
        cur.execute("""
            SELECT
              file_path,
              mime_type,
              uploaded_at
            FROM case_hearing_media
            WHERE blotter_case_id = %s
              AND media_kind = 'PHOTO'
              AND (%s IS NULL OR submission_id = %s)
            ORDER BY uploaded_at DESC
        """, [case_id, submission_id, submission_id])

        for file_path, mime_type, uploaded_at in cur.fetchall():
            path = file_path or ""
            # If already a full URL (Supabase public), use it as-is.
            if path.startswith("http://") or path.startswith("https://"):
                display_url = path
            else:
                # Legacy/local storage path under MEDIA_URL
                from django.conf import settings
                media_url = getattr(settings, "MEDIA_URL", "/media/")
                if not media_url.endswith("/"):
                    media_url += "/"
                display_url = media_url + path.lstrip("/")

            rows.append({
                # no 'id' field needed by the template
                "file_path": path,
                "display_url": display_url,
                "mime_type": mime_type,
                "uploaded_at": uploaded_at,
            })
    return rows





def _list_case_photos(case_id: int):
    """Return recent PHOTO attachments (for UI gallery)."""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT case_hearing_media_id, file_path, caption, uploaded_at
            FROM case_hearing_media
            WHERE blotter_case_id = %s
              AND is_deleted = FALSE
              AND media_kind = 'PHOTO'
            ORDER BY uploaded_at DESC, case_hearing_media_id DESC
            LIMIT 60
        """, [case_id])
        rows = cur.fetchall()
    return [
        {"id": r[0], "file_path": r[1], "caption": r[2], "uploaded_at": r[3]}
        for r in rows
    ]





def _supabase_client():
    url = getattr(settings, "SUPABASE_URL", "") or ""
    key = getattr(settings, "SUPABASE_SERVICE_ROLE_KEY", "") or ""
    if not (isinstance(url, str) and url and isinstance(key, str) and key):
        raise RuntimeError("Supabase URL/Key are missing or invalid. Check settings/env.")
    return create_client(url, key)


