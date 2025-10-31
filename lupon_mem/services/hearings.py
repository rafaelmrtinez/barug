# lupon_mem/services/hearings.py
from __future__ import annotations
from typing import Optional, Tuple
from django.utils import timezone
from ..db import q, q1, exec_only

def get_case_num(case_id: int) -> str:
    row = q1("SELECT case_num FROM blotter_case WHERE blotter_case_id=%s", (case_id,))
    return row[0] if row else f"{case_id}"

def mark_mediation_held(
    *, case_id: int, submission_id: Optional[int],
    compl_attended: bool, resp_attended: bool,
    settlement: Optional[str], held_remarks: Optional[str]
) -> Tuple[bool, str]:
    """
    Wrap whatever SQL you currently run inside this service.
    Keep the same behavior—just centralize it.
    """
    # Example (adjust to your real schema):
    exec_only("""
        UPDATE blotter_kp_submission
           SET hearing_held = TRUE,
               held_at = now(),
               held_remarks = COALESCE(%s, held_remarks),
               complainant_attended = %s,
               respondent_attended = %s,
               settlement_outcome = COALESCE(%s, settlement_outcome)
         WHERE submission_id = COALESCE(%s, submission_id)
           AND blotter_case_id = %s
    """, (held_remarks, compl_attended, resp_attended, settlement, submission_id, case_id))
    return True, "Mediation marked as held."

def mark_conciliation_held(
    *, case_id: int, submission_id: Optional[int],
    compl_attended: bool, resp_attended: bool,
    settlement: Optional[str], held_remarks: Optional[str]
) -> Tuple[bool, str]:
    # Same pattern; split if your SQL differs from mediation.
    exec_only("""
        UPDATE blotter_kp_submission
           SET hearing_held = TRUE,
               held_at = now(),
               held_remarks = COALESCE(%s, held_remarks),
               complainant_attended = %s,
               respondent_attended = %s,
               settlement_outcome = COALESCE(%s, settlement_outcome)
         WHERE submission_id = COALESCE(%s, submission_id)
           AND blotter_case_id = %s
    """, (held_remarks, compl_attended, resp_attended, settlement, submission_id, case_id))
    return True, "Conciliation marked as held."
