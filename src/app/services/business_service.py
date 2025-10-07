import os
import uuid
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import asdict
from django.conf import settings
from dataclasses import replace
from authentication.supabase_client import supabase
# from src.app.transfer_objects.dto.business_dto import BusinessListDTO
# from src.app.contracts.business_service_contract import IBusinessService
# from src.domain.contracts.business_repository_contract import IBusinessRepository

from src.app.transfer_objects.commands.business_cmd import (
    RegisterBusinessProfileCmd,
)
from src.app.transfer_objects.dto.business_dto import (
    BusinessListDTO,
    ResidentOwnerDTO,
)
from src.app.contracts.business_service_contract import (
    IBusinessService,
    IResidentOwnerService,
    IBusinessRegistrationService,
)
from src.domain.contracts.business_repository_contract import (
    IBusinessRepository,
    IResidentOwnerRepository,
)

class BusinessService(IBusinessService): 
    def __init__(
        self,
        business_repository: IBusinessRepository,
    ):
        self._business_repo = business_repository

    def execute(
        self,
        search: Optional[str] = None,
        b_type: Optional[str] = None,
        ownership_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[BusinessListDTO]:
        if search:
            return self._business_repo.search_business(search)
        if b_type is not None:
            return self._business_repo.sort_b_type(b_type)
        if ownership_type is not None:
            return self._business_repo.sort_ownership_type(ownership_type)
        if status is not None:
            return self._business_repo.sort_status(status)
        
        return self._business_repo.fetch_business_list()
    
class ResidentOwnerService(IResidentOwnerService):
    def __init__(
        self,
        resident_owner_repository: IResidentOwnerRepository,
    ):
        self._residentowner_repo = resident_owner_repository

    def execute(
        self, 
        search: Optional[str] = None, 
    ) -> list[ResidentOwnerDTO]:
        if not search or not str(search).strip():
            return []
        return self._residentowner_repo.search_owner(search=search.strip())
    
    def get_owner_details(self, person_id: int)-> Optional[ResidentOwnerDTO]:
        if not person_id:
            return None
        return self._residentowner_repo.get_owner_details(int(person_id))

class BusinessRegistrationService(IBusinessRegistrationService):
    def __init__(
        self,
        registration_repo: IBusinessRepository,
    ):
        self._registration_repo = registration_repo

    def _bucket_name(self) -> str:
        return getattr(settings, "SUPABASE__BUSINESS_PROOF_BUCKET")
    
    def _ensure_bucket(
        self,
        bucket: str,
        public: bool = True,
    ) -> None:
        """
        Best effort: create bucket if missing. Requires service key.
        Safe to no-op if bucket already exists or perms are limited.
        """
        try:
            # supabase-py v2
            existing = [b.name if hasattr(b, "name") else b["name"] for b in supabase.storage.list_buckets()]
            if bucket not in existing:
                try:
                    supabase.storage.create_bucket(bucket, public=public)
                except Exception:
                    # If you don't have permission or it already exists, just continue.
                    pass
        except Exception:
            # Older client fallback: ignore
            pass

    def _upload_file(self, bucket: str, uf) -> Optional[str]:
        """
        Upload a single Django UploadedFile to Supabase Storage.
        Returns storage path like: 'YYYY/MM/DD/<uuid>.<ext>' or None on failure.
        """
        if not uf:
            return None
        
        # Build a clean storage path
        _, ext = os.path.splitext(uf.name or "")
        ext = (ext or "").lower()
        key = f"{uuid.uuid4().hex}{ext}"
        # Optional: nest by date for tidy buckets
        from datetime import datetime
        today = datetime.utcnow().strftime("%Y/%m/%d")
        path_in_bucket = f"{today}/{key}"

        # Read bytes & detect content type
        data = uf.read()
        content_type = getattr(uf, "content_type", None) or "application/octet-stream"

        # supabase-py diverged across versions; try v2 signature first
        try:
            # v2: upload(file=<bytes|FileIO>, path=<str>, file_options={...})
            supabase.storage.from_(bucket).upload(
                file=data,
                path=path_in_bucket,
                file_options={"contentType": content_type, "upsert": True},
            )
        except TypeError:
            # v1-style: upload(<path>, <bytes>, options)
            supabase.storage.from_(bucket).upload(
                path_in_bucket, data, {"content-type": content_type, "x-upsert": "true"}
            )
        except Exception as e:
            # Log if you like; return None so caller can decide
            # print(f"Supabase upload failed: {e}")
            return None

        # Store the canonical storage path "<bucket>/<path>"
        return f"{bucket}/{path_in_bucket}"
    
    def _save_to_supabase(self, uploads: Optional[List]) -> List[str]:
        if not uploads:
            return []
        bucket = self._bucket_name()
        self._ensure_bucket(bucket, public=True)

        saved: List[str] = []
        for uf in (uploads if isinstance(uploads, (list, tuple)) else [uploads]):
            p = self._upload_file(bucket, uf)
            if p:
                saved.append(p)
        return saved
    
    def _save_proofs(self, uploads) -> List[str]:
        if not uploads:
            return []
        saved = []
        for f in uploads:
            # Save each file to your storage; return a stable key/path
            # Example placeholder:
            key = f"business-proofs/{f.name}"
            # self.storage.storage.from_("business-proofs").upload(key, f)   # your real save
            saved.append(key)
        return saved
    
    def business_registration(self, cmd: RegisterBusinessProfileCmd) -> Tuple[int, int]:
        # 1) Upload any provided files to Supabase
        # saved_paths = self._save_to_supabase(cmd.proof_files_uploads)

        # 1) Save uploads (if any) and collect final keys/paths
        saved_paths: List[str] = self._save_proofs(cmd.proof_files_uploads)

        # 2) Hand the saved storage paths to the repo (TEXT[] into your SQL function)
        # cmd.proof_files_saved = saved_paths

        # 2) DO NOT mutate cmd; create a new one with the saved paths
        cmd2 = replace(cmd, proof_files_saved=tuple(saved_paths))

        # 3) Proceed with DB registration
        # return self._registration_repo.register_business(cmd)
    
        # 3) Hand off to repo
        return self._registration_repo.register_business(cmd2)
