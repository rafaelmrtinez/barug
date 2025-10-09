import os
import uuid
import logging
logger = logging.getLogger(__name__)
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import asdict
from django.conf import settings
from dataclasses import replace
from authentication.supabase_client import supabase
from src.infra.exceptions.query_exec_exception import QueryExecutionException
# from src.app.transfer_objects.dto.business_dto import BusinessListDTO
# from src.app.contracts.business_service_contract import IBusinessService
# from src.domain.contracts.business_repository_contract import IBusinessRepository

from src.app.transfer_objects.commands.business_cmd import (
    RegisterBusinessProfileCmd,
)
from src.app.transfer_objects.dto.business_dto import (
    BusinessListDTO,
    ResidentOwnerDTO,
    OwnerBusinessDTO
)
from src.app.contracts.business_service_contract import (
    IBusinessService,
    IResidentOwnerService,
    IBusinessRegistrationService,
    IBusinessInfoService,
)
from src.domain.contracts.business_repository_contract import (
    IBusinessRepository,
    IResidentOwnerRepository,
)
from src.infra.repositories.business_repository import (
    OwnerBusinessInformationRepository,
)
from src.infra.storage.supabase_storage import SupabaseStorage

class BusinessService(IBusinessService): 
    def __init__(
        self,
        business_repository: IBusinessRepository,
    ):
        self._business_repo = business_repository

    def execute(
        self,
        search: Optional[str] = None,
        b_category: Optional[str] = None,
        ownership_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[BusinessListDTO]:
        if search:
            return self._business_repo.search_business(search)
        if b_category is not None:
            return self._business_repo.sort_b_type(b_category)
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
        return getattr(settings, "SUPABASE__BUSINESS_PROOF_BUCKET","business-proofs",)
    
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
        if not uf:
            return None

        from datetime import datetime
        _, ext = os.path.splitext(uf.name or "")
        ext = (ext or "").lower()
        key = f"{uuid.uuid4().hex}{ext}"
        path_in_bucket = f"{datetime.utcnow():%Y/%m/%d}/{key}"

        data = uf.read()
        content_type = getattr(uf, "content_type", None) or "application/octet-stream"

        try:
            supabase.storage.from_(bucket).upload(
                file=data,
                path=path_in_bucket,
                file_options={"contentType": content_type, "upsert": True},
            )
        except TypeError:
            supabase.storage.from_(bucket).upload(
                path_in_bucket, data, {"content-type": content_type, "x-upsert": "true"}
            )
        except Exception:
            return None
        
        logger.info("Uploaded to '%s': %s", bucket, path_in_bucket)
        print(f"[UPLOAD] {bucket}/{path_in_bucket}") 
        # ✅ return ONLY the path inside the bucket
        return path_in_bucket
    
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
                public_url = f"/storage/v1/object/public/{bucket}/{p}"
                logger.info("Public URL: %s", public_url)
                print(f"[PUBLIC URL] {public_url}")
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

        logger.info("Saved proof paths: %s", saved_paths)
        print(f"[SAVED PATHS] {saved_paths}")

        # 2) DO NOT mutate cmd; create a new one with the saved paths
        cmd2 = replace(cmd, proof_files_saved=tuple(saved_paths))

        # 3) Proceed with DB registration
        # return self._registration_repo.register_business(cmd)
    
        # 3) Hand off to repo
        return self._registration_repo.register_business(cmd2)

class OwnerBusinessInfoService(IBusinessInfoService):
    def __init__(
        self,
        owner_business_repo: OwnerBusinessInformationRepository,
        storage_repo: Optional[SupabaseStorage] = None,
    ):
        self._owner_business_repo = owner_business_repo
        self._storage = storage_repo or SupabaseStorage()

    # ---------- helpers for fallbacks ----------
    @staticmethod
    def _files_from_paths(paths: list[str] | None) -> list[dict]:
        """
        Normalize a list of file paths (from DB arrays) to the unified item shape.
        (No signing here because we don't know the bucket/object key reliably.)
        """
        files = []
        if not paths:
            return files
        for p in paths:
            if not p:
                continue
            name = p.split("/")[-1]
            # Keep shape consistent with storage results
            files.append({
                "name": name,
                "path": p,
                "size": None,
                "updated_at": None,
                "signed_url": None,  # unknown bucket/key; UI can still open if public URL
            })
        return files
    
    # @staticmethod
    # def _merge_owner_id_block(storage_block: dict, owner_row: dict) -> dict:
    #     """
    #     If storage is empty, fall back to valid_id_files[]/selfie_file from owner_row.
    #     Returns {"files": [...]} or {}.
    #     """
    #     # Prefer storage
    #     if storage_block and storage_block.get("files"):
    #         return storage_block

    #     files: list[dict] = []

    #     # Fallback: array of file paths
    #     valid_id_files = owner_row.get("valid_id_files") if owner_row else None
    #     files.extend(OwnerBusinessInfoService._files_from_paths(valid_id_files))

    #     # Optional: include selfie_file as a single-item entry
    #     selfie_path = owner_row.get("selfie_file") if owner_row else None
    #     if selfie_path:
    #         files.extend(OwnerBusinessInfoService._files_from_paths([selfie_path]))

    #     return {"files": files} if files else {}
    
    @staticmethod
    def _merge_business_proof_block(storage_block: dict, biz_row: dict) -> dict:
        """
        If storage is empty, fall back to proof_images[] from business_row.
        Returns {"files": [...]} or {}.
        """
        if storage_block and storage_block.get("files"):
            return storage_block

        proof_images = biz_row.get("proof_images") if biz_row else None
        files = OwnerBusinessInfoService._files_from_paths(proof_images)
        return {"files": files} if files else {}

    def execute(self, person_id: int, business_id: int) -> OwnerBusinessDTO:
        # 1) DB rows
        owner_row = self._owner_business_repo.get_owner_information(person_id)
        business_row = self._owner_business_repo.get_business_information(business_id)

        # 2) Storage lookups (Supabase)
        # Get supabase_uid if your get_details returns it; if not, consider adding it there.
        # supabase_uid = (owner_row or {}).get("supabase_uid")
        # owner_person_id = (owner_row or {}).get("person_id")
        # storage_owner_id = self._storage.get_owner_id_assets_any(supabase_uid, owner_person_id)
        storage_biz_proof = self._storage.get_business_proof_assets(business_id)

        # 3) Merge with fallbacks
        business_proof_block = self._merge_business_proof_block(storage_biz_proof, business_row or {})

        return OwnerBusinessDTO(
            owner= owner_row or {},
            business= business_row or {},
            business_proof= business_proof_block or {},
        )
    
    def execute_by_business_id(self, business_id: int) -> OwnerBusinessDTO:
        biz = self._owner_business_repo.get_business_information(business_id) or {}
        person_id = biz.get("owner_person_id")
        if not person_id:
            # If your DB function uses a different field name, adjust here
            raise QueryExecutionException("Owner (person_id) not found for this business.")
        return self.execute(person_id=int(person_id), business_id=business_id)
