from __future__ import annotations
from typing import Dict, Any
from django.template.loader import render_to_string
from common.send_email import send_email

def _owner_name(owner: Dict[str, Any]) -> str:
    last = (owner.get("last_name") or "").strip()
    first = (owner.get("first_name") or "").strip()
    mid = (owner.get("middle_name") or "").strip()
    suffix = (owner.get("suffix") or "").strip()
    parts = []
    if last: parts.append(last.upper())
    if first: parts.append(", " + first.title())
    if mid: parts.append(" " + (mid[0].upper() + "."))
    if suffix: parts.append(" " + suffix.upper())
    return "".join(parts) or (owner.get("full_name") or "").strip() or "Business Owner"

def notify_registration_received(
    *,
    owner: Dict[str, Any],
    business: Dict[str, Any],
    business_id: int,
) -> bool:
    """
    Sends an acknowledgement email after a business is registered.
    Returns True/False. Never raises (fail_silently=True).
    """
    owner_email = (owner.get("email") or "").strip()
    if not owner_email:
        # nothing to send to—treat as success to avoid blocking the flow
        return True

    ctx = {
        "owner_name": _owner_name(owner),
        "b_name": (business.get("b_name") or "your business").strip() or "your business",
        "business_id": business_id,
        "ref_code": f"BUS-{business_id:06d}",
        "pickup_hint": "Sign in to the mobile app to request the necessary business documents.",
    }

    # Prefer a Django template if present; otherwise fall back to inline HTML
    try:
        html = render_to_string("business/business_registration_received.html", ctx)
    except Exception:
        html = f"""
        <p>Hi {ctx['owner_name']},</p>
        <p>Your business <strong>{ctx['b_name']}</strong> has been recorded with the business #
        <strong>{ctx['ref_code']}</strong>.</p>
        <p>{ctx['pickup_hint']}</p>
        <p>— Barangay Sto. Niño</p>
        """

    text = (
        f"Hi {ctx['owner_name']},\n"
        f"Your business '{ctx['b_name']}' has been recorded.\n"
        f"Reference: {ctx['ref_code']}\n"
        f"{ctx['pickup_hint']}\n"
        f"— Barangay Sto. Niño"
    )

    res = send_email(
        subject=f"Business Registration Received — {ctx['ref_code']}",
        to=[(ctx["owner_name"], owner_email)],
        body_text=text,
        body_html=html,
        from_name="Barangay Sto. Niño",
        reply_to=["clerk@barangay.test"],
        fail_silently=True,  # don't block the UX if SMTP hiccups
    )
    return bool(res.ok)
