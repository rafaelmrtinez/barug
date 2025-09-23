from __future__ import annotations
from typing import Iterable, List, Tuple, Optional, Any
from types import SimpleNamespace
from email.utils import formataddr

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection

def _coerce_recipients(to: Iterable[Any]) -> Tuple[List[str], List[Tuple[str, str]]]:
    """
    Accept ['a@x.com', ('Name','b@x.com')] and return:
      (['a@x.com','b@x.com'], [('','a@x.com'), ('Name','b@x.com')])
    """
    flat: List[str] = []
    pairs: List[Tuple[str, str]] = []
    for item in to or []:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            name, email = item
            email = (email or "").strip()
            if email:
                flat.append(email)
                pairs.append((str(name or ""), email))
        else:
            email = str(item or "").strip()
            if email:
                flat.append(email)
                pairs.append(("", email))
    return flat, pairs

def send_email(
    *,
    subject: str,
    to: Iterable[Any],
    body_text: str,
    body_html: Optional[str] = None,
    from_email: Optional[str] = None,
    from_name: Optional[str] = None,
    reply_to: Optional[Iterable[str]] = None,
    attachments: Optional[Iterable[Tuple[str, bytes, str]]] = None,
    fail_silently: bool = False,
) -> SimpleNamespace:
    """
    Thin wrapper over Django email that always returns SimpleNamespace(ok=bool, detail=str).
    """
    # Choose sender
    sender_email = from_email or getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "EMAIL_HOST_USER", None)
    if not sender_email:
        return SimpleNamespace(ok=False, detail="No sender address configured (DEFAULT_FROM_EMAIL / EMAIL_HOST_USER).")
    sender_display = formataddr((from_name or "", sender_email))

    to_list, pairs = _coerce_recipients(to)
    if not to_list:
        return SimpleNamespace(ok=False, detail="Empty recipient list.")

    # --- DEBUG: show basics (no secrets) ---
    try:
        print("[EMAIL DEBUG] send_email()")
        print(f"  MAIL BACKEND : {getattr(settings, 'EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')}")
        print(f"  SMTP HOST    : {getattr(settings,'EMAIL_HOST','<unset>')}:{getattr(settings,'EMAIL_PORT','<unset>')}, TLS={getattr(settings,'EMAIL_USE_TLS',None)}, SSL={getattr(settings,'EMAIL_USE_SSL',None)}")
        print(f"  FROM         : {sender_display}")
        print(f"  TO           : {to_list}")
        if reply_to:
            print(f"  REPLY-TO     : {list(reply_to)}")
    except Exception:
        pass

    try:
        connection = get_connection(fail_silently=fail_silently)
        msg = EmailMultiAlternatives(
            subject=subject,
            body=body_text,
            from_email=sender_display,
            to=to_list,
            reply_to=list(reply_to or []),
            connection=connection,
        )
        if body_html:
            msg.attach_alternative(body_html, "text/html")
        for att in attachments or []:
            # att: (filename, bytes, mimetype)
            msg.attach(*att)

        sent = msg.send()
        return SimpleNamespace(ok=bool(sent), detail=f"sent={sent}")
    except Exception as e:
        if not fail_silently:
            raise
        return SimpleNamespace(ok=False, detail=str(e))
