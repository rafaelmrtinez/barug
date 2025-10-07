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

    # ✅ NEW: owner ID docs (non-resident owner flow)
    owner_valid_id_type_id: Optional[int] = None
    owner_id_front_path: Optional[str] = None
    owner_id_back_path: Optional[str] = None