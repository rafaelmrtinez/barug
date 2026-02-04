from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import json
import logging

from django.utils import timezone
from django.conf import settings

from authentication.supabase_client import supabase
from common.send_email import send_email

logger = logging.getLogger(__name__)

def _format_rcpt(rcpt: Any) -> str:
    try:
        if isinstance(rcpt, (list, tuple)) and len(rcpt) == 2:
            name, email = rcpt
            return f"{name} <{email}>" if name else str(email)
    except Exception:
        pass
    return str(rcpt)

def _debug_email_preview(subject: str, to_list: List[Any], body_txt: str, body_html: str | None) -> None:
    try:
        print("\n" + "=" * 72)
        print("[EMAIL DEBUG] Ready-for-pickup payload")
        print(f"Subject : {subject}")
        print(f"To      : {[ _format_rcpt(t) for t in to_list ]}")
        print("- TEXT ---------------------------------------------------")
        print(body_txt.rstrip())
        print("- HTML (first 600 chars) --------------------------------")
        snippet = (body_html or "")[:600]
        print(snippet.rstrip())
        if body_html and len(body_html) > 600:
            print("... [truncated]")
        print("=" * 72 + "\n")
    except Exception as e:
        logger.warning("Failed to print email preview: %s", e)

def _lookup_person_contact(person_id: Optional[int]) -> Tuple[Optional[str], Optional[str]]:
    """Return (full_name, email) for a given person_id from `person` table."""
    if not person_id:
        print("[EMAIL DEBUG] lookup: no person_id provided")
        return None, None
    try:
        res = (
            supabase
            .table("person")
            .select("first_name,last_name,email")
            .eq("person_id", person_id)
            .limit(1)
            .execute()
        )
        row = (res.data or [None])[0] or {}
        first = (row.get("first_name") or "").strip()
        last  = (row.get("last_name") or "").strip()
        full  = f"{first} {last}".strip() or None
        email = (row.get("email") or "").strip() or None
        print(f"[EMAIL DEBUG] lookup person_id={person_id} -> full_name={full!r}, email={email!r}")
        return full, email
    except Exception as e:
        logger.exception("Lookup failed for person_id=%s", person_id)
        print(f"[EMAIL DEBUG] lookup failed for person_id={person_id}: {e}")
        return None, None

def _resolve_person_id_from_header(header: Dict[str, Any]) -> Optional[int]:
    candidates = [
        header.get("requested_by_person_id"),
        header.get("on_behalf_of_person_id"),
        header.get("requester_person_id"),
        header.get("subject_person_id"),
        header.get("resident_person_id"),
        header.get("person_id"),
    ]
    for pid in candidates:
        if isinstance(pid, int) and pid > 0:
            return pid
    return None

def send_ready_for_pickup_email(header: Dict[str, Any], lines: List[Dict[str, Any]]) -> Tuple[bool, str]:
    person_id = _resolve_person_id_from_header(header)
    print(f"[EMAIL DEBUG] resolved person_id from header -> {person_id!r}")
    full_name, email = _lookup_person_contact(person_id)
    if not email:
        print("[EMAIL DEBUG] no email found on file; skipping send.")
        return False, "No email on file for this resident. Notification not sent."

    req_code = header.get("request_code") or f"REQ-{header.get('doc_request_id','')}"
    doc_names = [ (l.get("document_type_name") or "").strip() for l in (lines or []) ]
    doc_names = [d for d in doc_names if d]
    docs_str = ", ".join(doc_names) if doc_names else "your requested document(s)"

    barangay_name = getattr(settings, "BRGY_NAME", "Barangay Sto. Niño")
    pickup_info  = getattr(settings, "BRGY_PICKUP_INFO", "Please proceed to the Barangay Office during office hours.")

    subject = f"{barangay_name}: Request {req_code} is READY FOR PICKUP"
    body_html = f"""
        <p>Hi {full_name or 'Resident'},</p>
        <p>Your barangay document request <strong>{req_code}</strong> is now
        <strong>READY FOR PICKUP</strong>.</p>
        <p><b>Document(s):</b> {docs_str}</p>
        <p>{pickup_info}</p>
        <p>Thank you,<br>{barangay_name}</p>
    """
    body_txt = (
        f"Hi {full_name or 'Resident'},\n\n"
        f"Your barangay document request {req_code} is now READY FOR PICKUP.\n"
        f"Documents: {docs_str}\n\n"
        f"{pickup_info}\n\n"
        f"Thank you,\n{barangay_name}\n"
    )
    to_list = [(full_name or "", email)]

    _debug_email_preview(subject, to_list, body_txt, body_html)

    try:
        result = send_email(
            subject=subject,
            to=to_list,
            body_text=body_txt,
            body_html=body_html,
            from_name=barangay_name,
            fail_silently=False,
        )
        print(f"[EMAIL DEBUG] send_email result -> ok={getattr(result,'ok',None)!r}, detail={getattr(result,'detail',None)!r}")
        return (True, f"Email notification sent to {email}.") if getattr(result, "ok", False) \
               else (False, "Failed to send email notification at this time.")
    except Exception as e:
        print(f"[EMAIL DEBUG] send_email raised: {e}")
        logger.exception("send_email raised")
        return False, f"Email not sent: {e}"
