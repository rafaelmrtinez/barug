# bhw/health_views.py 
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from common.supabase_client import supabase
from common.verify_id import _upload_file, _public_url, verify_id_via_edge
import re
import json  # <<< added for pretty printing

# Expose role tuple so views.py can reuse in decorators
ROLE_BHW = ("BARANGAY HEALTH WORKER", "Barangay Health Worker", "bhw", "Super Admin")

# Map normalized id_type -> valid_id_type_id (extend as needed)
IDTYPE_TO_ID = {
    "ephil_id": 2,
    "philid": 2,
    "drivers_license": 6,
    # ...
}

# ---------- Shared helpers ----------

def normalize_id_type(id_type_raw: str) -> str:
    s = (id_type_raw or "").lower()
    s = s.replace("’", "").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")

def parse_csv_ints(s: Optional[str]) -> Optional[List[int]]:
    if not s:
        return None
    out: List[int] = []
    for tok in s.split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            out.append(int(tok))
        except Exception:
            continue
    return out or None

def _derive_bmi_status_id(weight: Optional[float], height_cm: Optional[float]) -> Optional[int]:
    """
    Safe fallback if UI didn't provide p_bmi_status_id.
    Returns: 1=Low, 2=Normal, 3=Overweight, 4=Obese
    """
    try:
        if not weight or not height_cm:
            return None
        h_m = float(height_cm) / 100.0
        if h_m <= 0:
            return None
        bmi = float(weight) / (h_m * h_m)
        if bmi < 18.5:   return 1
        if bmi < 25.0:   return 2
        if bmi < 30.0:   return 3
        return 4
    except Exception:
        return None

# ---------- Data access / RPC wrappers ----------

def search_residents(q: str) -> List[Dict[str, Any]]:
    if len(q) < 2:
        return []
    try:
        resp = supabase.rpc("search_person_by_code_or_name", {"p_key": q}).execute()
        return resp.data or []
    except Exception:
        return []

def verify_valid_id(*, supabase_uid: str, legit_person_id: int, id_type_raw: str,
                    profile_name: str, front, back, selfie) -> Dict[str, Any]:
    if not (supabase_uid and legit_person_id and id_type_raw and profile_name and front and back and selfie):
        return {"ok": False, "status": 400, "error": "Missing required fields/files."}

    id_type_code = normalize_id_type(id_type_raw)
    valid_id_type_id = IDTYPE_TO_ID.get(id_type_code)
    if not valid_id_type_id:
        return {"ok": False, "status": 400, "error": f'ID type "{id_type_code}" is not mapped to a valid_id_type_id.'}

    base = f"person/{supabase_uid}"
    front_key = f"{base}/front.jpg"
    back_key  = f"{base}/back.jpg"
    selfie_key = f"{base}/selfie.jpg"

    _upload_file(front, front.content_type, front_key)
    _upload_file(back, back.content_type, back_key)
    _upload_file(selfie, selfie.content_type, selfie_key)

    edge = verify_id_via_edge(
        supabase_uid=supabase_uid,
        profile_name=profile_name,
        id_type_code=id_type_code,
        front_path=front_key,
        back_path=back_key,
        selfie_path=selfie_key,
    )
    if not edge.ok:
        return {"ok": False, "status": getattr(edge, "status", 422), "edge": getattr(edge, "data", None)}

    front_url = _public_url(front_key)
    back_url  = _public_url(back_key)
    selfie_url = _public_url(selfie_key)

    rpc = supabase.rpc(
        "insert_valid_id",
        {
            "p_person_id": legit_person_id,
            "p_valid_id_type_id": valid_id_type_id,
            "p_selfie_path": selfie_url,
            "p_valid_id_front": front_url,
            "p_valid_id_back": back_url,
        },
    ).execute()

    if getattr(rpc, "error", None):
        return {"ok": False, "status": 500, "error": str(rpc.error)}

    return {"ok": True, "status": getattr(edge, "status", 200), "edge": getattr(edge, "data", None)}

def build_maternal_payload(cd: Dict[str, Any], staff_id: Optional[int]) -> Dict[str, Any]:
    """
    Minimal argument object for create_maternal_health_record_bhw.
    Mirrors the function signature exactly.
    """
    payload = {
        "p_added_by_id": int(staff_id) if staff_id else None,
        "p_person_id": int(cd["person_id"]),
        "p_husband_id": int(cd["husband_id"]) if cd.get("husband_id") else None,
    }

    try:
        print("\n[BHW] build_maternal_payload → payload:")
        import json as _json
        print(_json.dumps(payload, indent=2, default=str))
    except Exception:
        pass

    return payload

def create_maternal_record(payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Call the correct RPC and strictly pass only its 3 parameters.
    Includes a small shim for legacy 'p_staff_id'.
    """
    # Legacy shim
    if "p_staff_id" in payload and "p_added_by_id" not in payload:
        payload["p_added_by_id"] = payload.pop("p_staff_id")
        print("[BHW] NOTE: mapped legacy key p_staff_id → p_added_by_id")

    # Keep only the args your SQL function accepts
    allowed = {"p_added_by_id", "p_person_id", "p_husband_id"}
    payload = {k: payload.get(k) for k in allowed}

    try:
        print("\n[BHW] create_maternal_record → RPC payload (sanitized):")
        import json as _json
        print(_json.dumps(payload, indent=2, default=str))
    except Exception:
        pass

    try:
        res = supabase.rpc("create_maternal_health_record_bhw", payload).execute()
        print("[BHW] RPC create_maternal_health_record_bhw → data :", getattr(res, "data", None))
        print("[BHW] RPC create_maternal_health_record_bhw → error:", getattr(res, "error", None))
        if getattr(res, "error", None):
            return False, getattr(res.error, "message", str(res.error))
        return True, None
    except Exception as e:
        print("[BHW] RPC create_maternal_health_record_bhw → exception:", e)
        return False, str(e)

# ---------- Demo data used by UI (replace later with DB) ----------

def sample_registry() -> List[Dict[str, Any]]:
    return [
        {"id": 1, "name": "Maria Santos",  "family_no": "F-001", "ufc_no": "",       "purok": "Kanipaan", "kind": "maternal"},
        {"id": 2, "name": "Jethro Santos", "family_no": "F-002", "ufc_no": "UFC-12", "purok": "Kanipaan", "kind": "child"},
        {"id": 3, "name": "Ana Rivera",    "family_no": "F-010", "ufc_no": "",       "purok": "Pampango", "kind": "maternal"},
    ]

def detail_maternal(pk: int) -> Dict[str, Any]:
    return {
        "id": pk, "kind": "maternal", "name": "Maria Santos", "age": 28,
        "family_no": "F-001", "address": "Purok Kanipaan",
        "present": {"gravida": 2, "para": 1, "lmp": "2025-05-01", "edc": "2026-02-05"},
        "tt": [{"dose": "TT1", "date": "2024-11-10"}, {"dose": "TT2", "date": "2025-01-12"}],
        "anc": [{"date": "2025-06-10", "ga": "8w", "bp": "110/70", "wt": "54 kg", "fht": "—", "remarks": "Initial"}],
        "labs": {"Urinalysis": "Normal", "Syphilis": "NR"},
        "ogct_50": "85 mg/dL", "ogct_100": "—",
        "plan_delivery": "NSVD – District Hospital", "plan_nbs": True,
    }

def detail_child(pk: int) -> Dict[str, Any]:
    return {
        "id": pk, "kind": "child", "name": "Jethro Santos", "sex": "M",
        "family_no": "F-002", "ufc_no": "UFC-12", "dob": "2025-02-03", "birth_order": 1,
        "place_of_delivery": "Hospital (Gov’t)", "birth_weight": "3.2 kg",
        "feeding": "Exclusive BF", "mother": "Maria Santos", "father": "Joel Santos",
        "immunizations": [{"name": "BCG", "doses": ["2025-02-04", "", "", ""]}],
        "visits": [{"date": "2025-03-10", "age": "1 mo", "wt": "4.0 kg", "temp": "36.6", "ht": "54 cm", "findings": "Healthy", "notes": "—"}],
    }

def get_record_detail(kind: str, record_id: int) -> Dict[str, Any]:
    return detail_maternal(record_id) if kind == "maternal" else detail_child(record_id)
