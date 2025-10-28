from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple, IO, Optional

@dataclass(frozen=True)
class RegisterBusinessProfileCmd:
    owner: Dict[str, Any]
    business: Dict[str, Any]
    performer_staff_id: int

   # NEW: raw Django UploadedFile objects from the form
    proof_files_uploads: List[IO] = field(default_factory=list)

    # NEW: will be filled by the service after uploading to Supabase
    proof_files_saved: Tuple[str, ...] = field(default_factory=tuple)

@dataclass(frozen=True)
class CreateRenewalRequestCmd:
    business_id: int
    period_type: str          # 'ANNUAL' | 'QUARTERLY'
    period_year: int
    period_quarter: Optional[int]  # None for ANNUAL
    created_by_user_id: int
