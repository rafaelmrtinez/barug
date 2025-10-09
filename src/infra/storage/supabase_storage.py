from __future__ import annotations

from typing import Optional, Dict, Any, List
from src.infra.exceptions.query_exec_exception import QueryExecutionException


class SupabaseStorage:
    """
    Minimal wrapper for Supabase Storage to:
      • list files in a folder
      • create signed URLs

    Adjust BUCKET names and PATH builders to match your actual structure.
    """

    # ---- CONFIG (adjust if your buckets/paths differ) ----
    # PERSON_BUCKET = "id-uploads"          # e.g., 'id-uploads'
    BUSINESS_BUCKET = "business-proofs"   # e.g., 'business-proofs'
    SIGNED_URL_EXPIRES = 60 * 15          # 15 minutes

    def __init__(self, _supabase=None):
        self.client = _supabase

    def _safe_client(self):
        if self.client is None:
            raise QueryExecutionException("Supabase client not initialized.")
        return self.client

    # ---- helpers ----
    @staticmethod
    def _norm_folder(path: str) -> str:
        """
        Normalize a folder path so it has no leading slash
        and no trailing slash (Supabase storage prefers plain segments).
        """
        if not path:
            return ""
        p = path.strip().lstrip("/").rstrip("/")
        return p

    # ---- PATH BUILDERS (tweak to your layout) ----
    @staticmethod
    def person_root_path_any(supabase_uid: Optional[str], person_id: Optional[int]) -> Optional[str]:
        # Prefer supabase_uid if provided; otherwise use person_id
        if supabase_uid:
            return f"person/{supabase_uid}"
        if person_id:
            return f"person/{person_id}"
        return None

    @staticmethod
    def business_proofs_path(business_id: int) -> str:
        # Store your proofs under: 'business/<id>/proofs'
        return f"business/{business_id}/proofs"

    # ---- CORE OPS ----
    def list_folder(self, bucket: str, folder: str) -> List[Dict[str, Any]]:
        """
        Returns a list of files with metadata from a folder (non-recursive).
        Each item -> {'name','id','updated_at','metadata':{'size':...}, ...}
        """
        client = self._safe_client()
        folder = self._norm_folder(folder)

        # IMPORTANT: in supabase-py v2, .list expects:
        #   list(path: str, options: Dict[str, Any])
        # Options keys follow camelCase like JS: limit, offset, sortBy, search
        res = client.storage.from_(bucket).list(
            folder,
            {
                "limit": 1000,
                "offset": 0,
                "sortBy": {"column": "name", "order": "asc"},
                # "search": "optional-filter"
            },
        )
        # Some client versions return [] directly; others return {"data":[...], "error":...}
        if isinstance(res, dict):
            # supabase-py sometimes returns dict with "data"
            data = res.get("data")
            return data or []
        return res or []

    def sign_url(self, bucket: str, path: str) -> Optional[str]:
        client = self._safe_client()
        try:
            clean = self._norm_folder(path)
            signed = client.storage.from_(bucket).create_signed_url(clean, self.SIGNED_URL_EXPIRES)
            # For supabase-py v2, returns {'signedURL': '...','path':'...'}
            if isinstance(signed, dict):
                return signed.get("signedURL")
            # Some builds return object with attribute access; be defensive:
            return getattr(signed, "signedURL", None)
        except Exception:
            return None

    # ---- High-level getters ----
    # def get_owner_id_assets_any(self, supabase_uid: Optional[str], person_id: Optional[int]) -> Dict[str, Any]:
    #     prefix = self.person_root_path_any(supabase_uid, person_id)
    #     if not prefix:
    #         return {}
    #     items = self.list_folder(self.PERSON_BUCKET, prefix) or []
    #     files: List[Dict[str, Any]] = []

    #     for it in items:
    #         name = (it or {}).get("name")
    #         if not name:
    #             continue
    #         # filter to common previewable/docs
    #         if not name.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".pdf")):
    #             continue
    #         path = f"{self._norm_folder(prefix)}/{name}"
    #         files.append(
    #             {
    #                 "name": name,
    #                 "path": path,
    #                 "size": ((it.get("metadata") or {}).get("size")),
    #                 "updated_at": it.get("updated_at"),
    #                 "signed_url": self.sign_url(self.PERSON_BUCKET, path),
    #             }
    #         )

    #     return {"files": files} if files else {}

    def get_business_proof_assets(self, business_id: int) -> Dict[str, Any]:
        """
        Returns:
          {
            "files": [
              {"name","path","size","updated_at","signed_url"}
            ]
          }
        """
        folder = self.business_proofs_path(business_id)
        items = self.list_folder(self.BUSINESS_BUCKET, folder) or []
        files: List[Dict[str, Any]] = []

        for it in items:
            if not it or not it.get("name"):
                continue
            name = it["name"]
            if not name.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".pdf")):
                continue

            path = f"{self._norm_folder(folder)}/{name}"
            signed = self.sign_url(self.BUSINESS_BUCKET, path)
            files.append(
                {
                    "name": name,
                    "path": path,
                    "size": ((it.get("metadata") or {}).get("size")),
                    "updated_at": it.get("updated_at"),
                    "signed_url": signed,
                }
            )

        return {"files": files} if files else {}
