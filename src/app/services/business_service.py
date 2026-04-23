import os
import uuid
import logging
logger = logging.getLogger(__name__)
from typing import Any, Dict, List, Optional, Tuple
from decimal import Decimal
from dataclasses import asdict
from django.conf import settings
from dataclasses import replace
from authentication.supabase_client import supabase
from src.infra.exceptions.query_exec_exception import QueryExecutionException

from src.app.transfer_objects.commands.business_cmd import (
    RegisterBusinessProfileCmd,
    CreateRenewalRequestCmd
)
from src.app.transfer_objects.dto.business_dto import (
    BusinessListDTO,
    ResidentOwnerDTO,
    OwnerBusinessDTO,
    RenewalListDTO,
    RenewalQuoteLineDTO
)
from src.app.contracts.business_service_contract import (
    IBusinessService,
    IResidentOwnerService,
    IBusinessRegistrationService,
    IBusinessInfoService,
    IBusinessRenewalService,
    IBusinessRenewalQuoteService,
    IBusinessRenewalRequestService,
    IBusinessClosurePaymentRequestService,
)
from src.domain.contracts.business_repository_contract import (
    IBusinessRepository,
    IResidentOwnerRepository,
    IBusinessRenewalRepository,
    IBusinessRenewalQuoteRepository,
    IBusinessRenewalRequestRepository,
    IBusinessClosurePaymentRequestRepository,
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
        b_category: Optional[int] = None,
        ownership_type: Optional[int] = None,
        status: Optional[int] = None,
    ) -> list[BusinessListDTO]:
        if search:
            return self._business_repo.search_business(search)
        if b_category is not None:
            return self._business_repo.sort_b_category(b_category)
        if ownership_type is not None:
            return self._business_repo.sort_ownership_type(ownership_type)
        if status is not None:
            return self._business_repo.sort_status(status)
        
        return self._business_repo.fetch_business_list()
    
    def execute_with_filters(self) -> list[BusinessListDTO]:
        """
        Fetches business list with additional fields for filtering.
        Use this for business_map_list view to enable purok, date_range, and employee_range filters.
        """
        return self._business_repo.fetch_business_list_with_filters()
    
    def check_business_duplicate(
        self,
        *,
        owner_person_id: int,
        business_name: str,
        city: str,
        barangay: str,
        street: str,
        purok_sitio_id: Optional[int],
        b_category_id: Optional[int],
    ) -> Optional[int]:
        if not owner_person_id or not (business_name and city and barangay and street):
            return None
        return self._business_repo.find_duplicate_business(
            owner_person_id=owner_person_id,
            business_name=business_name,
            city=city,
            barangay=barangay,
            street=street,
            purok_sitio_id=purok_sitio_id,
            b_category_id=b_category_id,
        )

class ResidentOwnerService(IResidentOwnerService):
    def __init__(
        self,
        resident_owner_repository: IResidentOwnerRepository,
    ):
        self._residentowner_repo = resident_owner_repository

    def execute(
        self, 
        search: Optional[str] = None, 
        only_nonresident: bool = False,
    ) -> list[ResidentOwnerDTO]:
        if not search or not str(search).strip():
            return []
        return self._residentowner_repo.search_owner(search=search.strip(), only_nonresident=only_nonresident)
    
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
        return getattr(settings, "SUPABASE_BUSINESS_PROOF_BUCKET","business-proofs",)
    
    def _ensure_bucket(self, bucket: str, public: bool = True) -> None:
        try:
            # list_buckets needs SERVICE key
            res = supabase.storage.list_buckets()
            names = [getattr(b, "name", None) or (b.get("name") if isinstance(b, dict) else None) for b in (res or [])]
            if bucket not in names:
                try:
                    supabase.storage.create_bucket(bucket, public=public)
                except Exception as e:
                    # If concurrent create or perms issue, just log and continue
                    print("[storage] create_bucket error:", e, flush=True)
        except Exception as e:
            # If list_buckets fails (permissions), you’re not using the service key
            print("[storage] list_buckets failed (service key?)", e, flush=True)

    def _upload_temp(self, bucket: str, uf) -> str | None:
        """Upload a single file to a temp folder. Returns its temp key (no domain)."""
        if not uf:
            return None
        from datetime import datetime
        import os, uuid
        _, ext = os.path.splitext(getattr(uf, "name", "") or "")
        ext = (ext or "").lower()
        key = f"{uuid.uuid4().hex}{ext}"
        temp_key = f"tmp/inbox/{datetime.utcnow():%Y/%m/%d}/{key}"

        data = uf.read()
        content_type = getattr(uf, "content_type", None) or "application/octet-stream"

        try:
            # supabase-py v2 style
            supabase.storage.from_(bucket).upload(
                file=data,
                path=temp_key,
                file_options={"contentType": content_type, "upsert": True},
            )
        except TypeError:
            # older signature fallback
            supabase.storage.from_(bucket).upload(temp_key, data, {"content-type": content_type, "x-upsert": "true"})
        return temp_key
    
    def _upload_many_temp(self, uploads: list) -> list[str]:
        if not uploads:
            return []
        bucket = self._bucket_name()
        self._ensure_bucket(bucket, public=True)
        keys: list[str] = []
        for uf in uploads:
            try:
                k = self._upload_temp(bucket, uf)
                if k:
                    keys.append(k)
            finally:
                try:
                    uf.close()
                except Exception:
                    pass
        return keys
    
    def _final_folder(self, business_id: int) -> str:
        return f"business/{business_id}/proofs"

    def _move_to_final(self, temp_keys: list[str], business_id: int) -> list[str]:
        """Move each temp object into business/<id>/proofs. Returns final keys."""
        if not temp_keys:
            return []
        bucket = self._bucket_name()
        dest_folder = self._final_folder(business_id)
        finals: list[str] = []
        for src in temp_keys:
            name = src.rsplit("/", 1)[-1]
            dst = f"{dest_folder}/{name}"
            try:
                # supabase-py exposes move in v2; if unavailable, copy+remove
                supabase.storage.from_(bucket).move(src, dst)
            except Exception:
                try:
                    # copy then remove as a fallback
                    supabase.storage.from_(bucket).copy(src, dst)
                    supabase.storage.from_(bucket).remove([src])
                except Exception:
                    continue
            finals.append(dst)
        return finals

    def business_registration(self, cmd: RegisterBusinessProfileCmd) -> tuple[int, int]:
        """
        1) Upload proofs to temp
        2) Create business in DB
        3) Move proofs under business/<id>/proofs
        4) Pass the FINAL keys to DB (if you want them stored), or skip if your UI lists from storage anyway.
        """
        # 1) upload to temp
        temp_keys = self._upload_many_temp(cmd.proof_files_uploads)

        # 2) make initial DB record first (without proofs)
        cmd_no_proofs = replace(cmd, proof_files_saved=tuple())
        business_id, owner_person_id = self._registration_repo.register_business(cmd_no_proofs)

        # 3) move to final folder tied to business_id
        final_keys = self._move_to_final(temp_keys, business_id)

        # 4) optionally, persist final_keys back to DB. If your RPC supports a separate
        #    "attach proofs" step, call it here. Otherwise, re-call register with proofs OR
        #    skip storing and rely on storage listing in your UI.
        #
        # If you want the keys stored, and your RPC accepts them, do:
        #   self._registration_repo.attach_business_proofs(business_id, final_keys)
        #
        # For your current UI, OwnerBusinessInfoService lists directly from storage,
        # so storing is optional. Still, we’ll return the same pair:
        return business_id, owner_person_id
    
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

class BusinessRenewalService(IBusinessRenewalService):
    def __init__(
        self,
        business_renewal_repo: IBusinessRenewalRepository,
    ):
        self._business_renewal_repo = business_renewal_repo

    def execute(
        self, 
        search: Optional[str] = None, 
        clearance_state: Optional[int] = None,
    ) -> list[RenewalListDTO]:
        if search:
            return self._business_renewal_repo.search_business_renewal(search)
        if clearance_state is not None:
            return self._business_renewal_repo.sort_clearance_sate(clearance_state)

        return self._business_renewal_repo.fetch_business_renewal_list()
    
class BusinessRenewalQuoteService(IBusinessRenewalQuoteService):
    def __init__(self, quote_repo: IBusinessRenewalQuoteRepository):
        self._quote_repo = quote_repo

    def execute(self, business_id: int, year: int) -> Tuple[Decimal, List[RenewalQuoteLineDTO], List[Dict[str, Any]]]:
        grand_total = self._quote_repo.fetch_grand_total_auto(business_id, year)
        quote_rows  = self._quote_repo.fetch_quote_auto(business_id, year)
        paid_rows   = self._quote_repo.fetch_paid_history(business_id)
        return (grand_total, quote_rows, paid_rows)
    
class BusinessRenewalRequestService(IBusinessRenewalRequestService):
    def __init__(self, repo: IBusinessRenewalRequestRepository):
        self._repo = repo

    def request_renewal(self, cmd: CreateRenewalRequestCmd) -> int:
        # (optional) small validations
        if cmd.period_type not in ("ANNUAL","QUARTERLY"):
            raise ValueError("period_type must be ANNUAL or QUARTERLY")
        if cmd.period_type == "ANNUAL":
            object.__setattr__(cmd, "period_quarter", None)  # force None
        return self._repo.request_renewal(cmd)
    
    def request_unpaid(self, cmd: CreateRenewalRequestCmd) -> List[int]:
        if cmd.period_type not in ("ANNUAL","QUARTERLY"):
            raise ValueError("period_type must be ANNUAL or QUARTERLY")
        if cmd.period_type == "ANNUAL":
            object.__setattr__(cmd, "period_quarter", None)
        return self._repo.request_unpaid(cmd)

class BusinessClosurePaymentRequestService(IBusinessClosurePaymentRequestService):
    def __init__(self, repo: IBusinessClosurePaymentRequestRepository):
        self._repo = repo

    def request_payment(self, cmd: CreateRenewalRequestCmd) -> int:
        if cmd.period_type not in ("ANNUAL","QUARTERLY"):
            raise ValueError("period_type must be ANNUAL or QUARTERLY")
        if cmd.period_type == "ANNUAL":
            object.__setattr__(cmd, "period_quarter", None)
        return self._repo.request_payment(cmd)

    def request_unpaid(self, cmd: CreateRenewalRequestCmd) -> list[int]:
        if cmd.period_type not in ("ANNUAL","QUARTERLY"):
            raise ValueError("period_type must be ANNUAL or QUARTERLY")
        if cmd.period_type == "ANNUAL":
            object.__setattr__(cmd, "period_quarter", None)
        return self._repo.request_unpaid(cmd)

