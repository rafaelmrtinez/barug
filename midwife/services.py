# midwife/services.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import re
import json

from common.supabase_client import supabase
from common.verify_id import _upload_file, _public_url, verify_id_via_edge

# ---------------- Constants / roles ----------------
ROLE_MIDWIFE = "MIDWIFE"

IDTYPE_TO_ID = {
    "ephil_id": 2,
    "philid": 2,
    "drivers_license": 6,
    # extend as needed...
}

# ---------------- Small helpers ----------------
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
    """1=Low, 2=Normal, 3=Overweight, 4=Obese; None if not computable."""
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

def _first_present(d: Dict[str, Any], *keys: str) -> Any:
    for k in keys:
        v = d.get(k)
        if v not in (None, "", []):
            return v
    return None

def _compose_name(row: Dict[str, Any]) -> str:
    """Build 'Last, First M. Suffix' (tolerates missing parts)."""
    ln = (row.get("last_name") or "").strip()
    fn = (row.get("first_name") or "").strip()
    mn = (row.get("middle_name") or "").strip()
    sx = (row.get("suffix") or "").strip()
    mid = f" {mn[0]}." if mn else ""
    suf = f" {sx}" if sx else ""
    base = (f"{ln}, {fn}{mid}{suf}").strip(", ").strip()
    return base or (row.get("person_code") or "—")

# ---------------- Data access wrappers ----------------
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
    weight = cd.get("weight")
    height = cd.get("height")
    bmi_status_id = int(cd["bmi_status_id"]) if cd.get("bmi_status_id") else None
    if bmi_status_id is None:
        try:
            w = float(weight) if weight not in (None, "") else None
            h = float(height) if height not in (None, "") else None
        except Exception:
            w = h = None
        bmi_status_id = _derive_bmi_status_id(w, h)

    payload = {
        # ✅ CHANGED: was "p_staff_id"
        "p_added_by_id": int(staff_id) if staff_id else None,
        "p_person_id": int(cd["person_id"]),
        "p_husband_id": int(cd["husband_id"]) if cd.get("husband_id") else None,
    }

    try:
        print("\n[BHW] build_maternal_payload → payload:")
        import json as _json
        print(_json.dumps(payload, indent=2, default=str))
    except Exception:
        print("[BHW] build_maternal_payload → (could not pretty-print payload)")

    return payload


def create_maternal_record(payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    # ✅ Backward-compat shim: if some caller still set p_staff_id, map it.
    if "p_staff_id" in payload and "p_added_by_id" not in payload:
        payload["p_added_by_id"] = payload.pop("p_staff_id")
        print("[BHW] NOTE: mapped legacy key p_staff_id → p_added_by_id")
    try:
        print("\n[BHW] create_maternal_record → RPC payload:")
        import json as _json
        print(_json.dumps(payload, indent=2, default=str))
    except Exception:
        print("[BHW] create_maternal_record → (could not pretty-print payload)")

    try:
        # ✅ CHANGED: call the new RPC name
        res = supabase.rpc("create_maternal_health_record_bhw", payload).execute()
        print("[BHW] RPC create_maternal_health_record_bhw → data :", getattr(res, "data", None))
        print("[BHW] RPC create_maternal_health_record_bhw → error:", getattr(res, "error", None))
        if getattr(res, "error", None):
            return False, getattr(res.error, "message", str(res.error))
        return True, None
    except Exception as e:
        print("[BHW] RPC create_maternal_health_record_bhw → exception:", e)
        return False, str(e)


# ---------------- NEW: fetch maternal registry for Records page ----------------
def fetch_maternal_registry(*, q: str = "", limit: int = 200) -> List[Dict[str, Any]]:
    """
    Pull rows from `maternal_health_record`, then enrich each row with the person's
    name / family_no / purok using your RPC `get_specific_resident_full_profile`.
    Returns items shaped for records.html: [{id, name, family_no, purok, kind}]
    """
    try:
        base = supabase.table("maternal_health_record").select("*").order("created_at", desc=True)
        if limit:
            base = base.limit(int(limit))
        resp = base.execute()
        rows: List[Dict[str, Any]] = resp.data or []
        print(f"[MIDWIFE] fetched maternal_health_record rows: {len(rows)}")
    except Exception as e:
        print("[MIDWIFE] error fetching maternal_health_record:", e)
        rows = []

    out: List[Dict[str, Any]] = []

    for r in rows:
        # Be defensive about keys
        rid = _first_present(r,
            "maternal_health_record_id", "maternal_record_id", "record_id", "id"
        )
        person_id = _first_present(r, "person_id", "p_person_id", "mother_id")

        # Get person details for display
        name = "—"
        family_no = None
        purok = None

        if person_id:
            try:
                prof = supabase.rpc("get_specific_resident_full_profile", {"p_person_id": int(person_id)}).execute()
                pdata = (prof.data or [])
                prow = pdata[0] if isinstance(pdata, list) and pdata else (pdata or {})  # tolerate single row or list
                name = _compose_name(prow)
                family_no = prow.get("family_num")
                purok = _first_present(prow, "sitio_purok_name", "purok_sitio_name")
            except Exception as e:
                print(f"[MIDWIFE] profile fetch failed for person_id={person_id}: {e}")

        item = {
            "id": rid,
            "name": name,
            "family_no": family_no,
            "purok": purok,
            "kind": "maternal",
        }
        out.append(item)

    # Simple search filter (client asked to be able to search)
    qnorm = (q or "").strip().lower()
    if qnorm:
        filtered = []
        for it in out:
            hay = " ".join([
                str(it.get("name") or ""),
                str(it.get("family_no") or ""),
                str(it.get("purok") or "")
            ]).lower()
            if qnorm in hay:
                filtered.append(it)
        out = filtered

    if not out:
        print("[MIDWIFE] No results for maternal registry list (after filters).")
    else:
        print(f"[MIDWIFE] Records to display: {len(out)}")
    return out

# ---------------- Demo detail helpers (kept) ----------------
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


# ---------- ANC visit insert (Midwife) ----------

def _to_num(x):
    try:
        if x in (None, "", "—"):
            return None
        return float(str(x).strip())
    except Exception:
        return None

def _trimester_stage_id_from_ga(ga_weeks: Optional[int]) -> Optional[int]:
    if ga_weeks is None:
        return None
    try:
        ga = int(ga_weeks)
    except Exception:
        return None
    if ga <= 13:
        return 1
    if ga <= 27:
        return 2
    return 3

def build_anc_visit_payload(
    *, record_id: int, form: Dict[str, Any], staff_id: Optional[int]
) -> Dict[str, Any]:
    """
    Shapes the POST from the Add-Visit modal to match the SQL function:
    insert_anc_visit_with_details(
      p_maternal_record_id, p_assessed_by_id, p_visit_date, p_trimester_stage_id,
      p_prev_illness, p_prev_hospitalization, p_prev_preg_complication,
      p_num_children_born_alive, p_num_children_living, p_num_abortion,
      p_num_stillbirth, p_num_large_babies, p_has_diabetes, p_prev_pregs,
      p_weight, p_height, p_bmi_status_id, p_newborn_plan, p_delivery_plan,
      p_gravida, p_para, p_is_fullterm, p_is_preterm, p_lmp, p_edc,
      p_lab_results, p_checklist_item_ids, p_risk_category_ids, p_tt_vaccines,
      p_iron_start_date, p_iron_end_date, p_deworming_date
    )
    """
    # modal fields
    visit_date = (form.get("visit_date") or "").strip() or None
    ga_weeks = form.get("ga_weeks")
    tri_id = _trimester_stage_id_from_ga(int(ga_weeks)) if ga_weeks not in (None, "", "—") else None

    # optional JSONs from hidden inputs
    try:
        labs = json.loads(form.get("labs_json") or "[]")
    except Exception:
        labs = []
    try:
        tts = json.loads(form.get("tt_json") or "[]")
    except Exception:
        tts = []
    # We don't have array<int> for checklist/risk from the modal; leave None
    # Danger signs are strings in `danger_signs_json` and don't map to numeric IDs here.

    payload = {
        "p_maternal_record_id": int(record_id),
        "p_assessed_by_id": int(staff_id) if staff_id else None,
        "p_visit_date": visit_date,
        "p_trimester_stage_id": tri_id,

        # baseline/history fields we don't collect in this modal → pass None
        "p_prev_illness": None,
        "p_prev_hospitalization": None,
        "p_prev_preg_complication": None,
        "p_num_children_born_alive": None,
        "p_num_children_living": None,
        "p_num_abortion": None,
        "p_num_stillbirth": None,
        "p_num_large_babies": None,
        "p_has_diabetes": None,
        "p_prev_pregs": None,

        # anthropometrics captured in the visit (weight only from modal)
        "p_weight": _to_num(form.get("weight_kg")),
        "p_height": None,
        "p_bmi_status_id": None,

        # plans / episode dates not in this modal
        "p_newborn_plan": None,
        "p_delivery_plan": None,
        "p_gravida": None,
        "p_para": None,
        "p_is_fullterm": None,
        "p_is_preterm": None,
        "p_lmp": None,
        "p_edc": None,

        # visit details available as JSON
        "p_lab_results": labs,
        "p_checklist_item_ids": None,
        "p_risk_category_ids": None,
        "p_tt_vaccines": tts,

        # supplements/vit mins/deworming — dates not captured here
        "p_iron_start_date": None,
        "p_iron_end_date": None,
        "p_deworming_date": None,
    }

    try:
        print("\n[MIDWIFE] build_anc_visit_payload →", json.dumps(payload, indent=2, default=str))
    except Exception:
        pass
    return payload


def insert_anc_visit_with_details(payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """RPC wrapper for insert_anc_visit_with_details."""
    try:
        print("\n[MIDWIFE] insert_anc_visit_with_details → RPC payload:")
        print(json.dumps(payload, indent=2, default=str))
    except Exception:
        pass

    try:
        res = supabase.rpc("insert_anc_visit_with_details", payload).execute()
        print("[MIDWIFE] RPC insert_anc_visit_with_details → data :", getattr(res, "data", None))
        print("[MIDWIFE] RPC insert_anc_visit_with_details → error:", getattr(res, "error", None))
        if getattr(res, "error", None):
            return False, getattr(res.error, "message", str(res.error))
        return True, None
    except Exception as e:
        print("[MIDWIFE] RPC insert_anc_visit_with_details → exception:", e)
        return False, str(e)
