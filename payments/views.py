from __future__ import annotations

import json
import requests
from urllib.parse import urlparse, unquote
from decimal import Decimal
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, Optional

from django.conf import settings
from django.http import (
    JsonResponse, HttpResponse, HttpResponseBadRequest
)
from django.views.decorators.csrf import csrf_exempt
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET

from .db import exec_sql, exec_one
from .utils import paymongo_auth_header, verify_paymongo_signature


# =============================== helpers ====================================

def _check_api_key(request) -> bool:
    """Optional internal protection for sensitive endpoints."""
    expected = getattr(settings, "INTERNAL_API_KEY", None)
    if not expected:
        return True
    return request.headers.get("X-API-Key") == expected


def _st(name: str) -> int:
    """Resolve a canonical status name to its ID via v_req_status."""
    row = exec_one(
        "select request_status_id from v_req_status where canonical_name=%s limit 1;",
        [name.upper()]
    )
    if not row:
        raise ValueError(f"request_status '{name}' not found in v_req_status")
    return row["request_status_id"]


def _log(action: str,
         table_affected: str,
         record_affected_id: int,
         details: Optional[Dict[str, Any]] = None,
         performer_staff_id: Optional[int] = None,
         performer_person_id: Optional[int] = None) -> None:
    """Thin wrapper around doc_log_event to avoid breaking the flow on log errors."""
    try:
        exec_sql(
            "select doc_log_event(%s,%s,%s,%s::jsonb,%s,%s);",
            [
                action,
                table_affected,
                record_affected_id,
                json.dumps(details or {}),
                performer_staff_id,
                performer_person_id,
            ],
        )
    except Exception:
        # Do not let logging failures break payment flows.
        pass


ALLOWED_APP_SCHEMES = {"barug", "exp", "exps", "exp+"}

def _sanitize_return_to(raw: Optional[str]) -> Optional[str]:
    """Allow only deep links (custom schemes) or safe https links if you use Universal Links."""
    if not raw:
        return None
    try:
        pr = urlparse(raw)
        if pr.scheme and pr.scheme in ALLOWED_APP_SCHEMES:
            return raw
        if pr.scheme in ("http", "https") and url_has_allowed_host_and_scheme(raw, allowed_hosts=None):
            return raw
    except Exception:
        pass
    return None


# ============================= Finalizers ===================================

def _payment_method_online_id() -> Optional[int]:
    # Prefer ONLINE_GCASH if present; else GCASH
    row = exec_one("""
      select payment_method_id
        from payment_method
       where method_name in ('ONLINE_GCASH','GCASH')
       order by case when method_name='ONLINE_GCASH' then 0 else 1 end
       limit 1;
    """)
    return row["payment_method_id"] if row else None


def _make_or_number_fallback(event_ref: str) -> str:
    try:
        r = exec_one("select make_or_number() as or_number;")
        if r and r["or_number"]:
            return r["or_number"]
    except Exception:
        pass
    return f"OR-{event_ref}"


def _finalize_doc_paid(doc_id: int, paid_dt, event_ref: str, provider_payment_id: Optional[str]):
    """
    Idempotent finalizer for document payments.
    Serializes on the latest payment_session row and avoids duplicate OR inserts.
    Also: after marking PAID, move to FOR_CLERK_REVIEW (unless RECONCILE).
    """
    # --- 0) Lock latest session to serialize concurrent finalizers (webhook vs redirect)
    lock = exec_one("""
      select payment_session_id, status
        from payment_session
       where doc_request_id=%s
       order by created_at desc
       limit 1
       for update
    """, [doc_id])
    if not lock:
        return

    # If already paid AND an OR already exists, bail early
    already_or = exec_one("""
      select 1
        from official_receipt
       where doc_request_id=%s
       limit 1
    """, [doc_id])
    if lock["status"] == "PAID" and already_or:
        return

    # --- 1) Mark latest session as PAID and fetch amounts
    ps = exec_one("""
      with x as (
        select payment_session_id
          from payment_session
         where doc_request_id=%s
         order by created_at desc
         limit 1
      )
      update payment_session ps
         set status='PAID',
             paid_at=%s,
             provider_payment_id = coalesce(%s, provider_payment_id)
        from x
       where ps.payment_session_id = x.payment_session_id
      returning ps.amount, ps.payment_session_id;
    """, [doc_id, paid_dt, provider_payment_id])

    if not ps:
        return

    # log: session paid (SYSTEM performer => pass None)
    _log(
        "PAYMENT_SESSION_PAID",
        "payment_session",
        ps["payment_session_id"],
        {
            "doc_request_id": doc_id,
            "provider_payment_id": provider_payment_id,
            "paid_at": str(paid_dt),
            "source": "ONLINE_PAYMENT",
        },
        None,
        None,
    )

    collected = Decimal(str(ps["amount"] or 0))
    server    = exec_one("select _doc_request_amount(%s) as amt;", [doc_id])
    server_amt = Decimal(str((server or {}).get("amt", 0)))

    pm_id  = _payment_method_online_id()
    or_no  = _make_or_number_fallback(event_ref)
    issuer = None  # allowed to be NULL (schema changed)

    # --- 2) If an OR already exists (race), skip issuing another
    exists_or = exec_one("""
      select or_id
        from official_receipt
       where doc_request_id=%s
       order by issued_at desc
       limit 1
    """, [doc_id])
    or_id = (exists_or or {}).get("or_id")

    if not or_id:
        # Issue OR for the collected amount (what the gateway charged)
        or_row = exec_one("""
          insert into official_receipt(
            or_number, issued_by_staff_id, doc_request_id, payment_method_id,
            amount_due, amount_paid, change_due
          ) values (%s, %s, %s, %s, %s, %s, 0)
          returning or_id;
        """, [or_no, issuer, doc_id, pm_id, float(collected), float(collected)])
        or_id = (or_row or {}).get("or_id")

        if or_id:
            _log(
                "PAYMENT_ACCEPTED",
                "official_receipt",
                or_id,
                {
                    "doc_request_id": doc_id,
                    "or_number": or_no,
                    "payment_method_id": pm_id,
                    "amount_due": float(collected),
                    "amount_paid": float(collected),
                    "change_due": 0,
                    "source": "ONLINE_PAYMENT",
                },
                None,
                None,
            )

    # --- 3) Always set to PAID first (idempotent)
    st_paid = _st("PAID")
    prev = exec_one(
        "select request_status_id from doc_request_hdr where doc_request_id=%s limit 1;",
        [doc_id]
    )
    prev_id = (prev or {}).get("request_status_id")

    if prev_id != st_paid:
        exec_sql("""
          update doc_request_hdr
             set request_status_id = %s,
                 current_status_set_at = now()
           where doc_request_id = %s;
        """, [st_paid, doc_id])

        _log(
            "STATUS_CHANGED",
            "doc_request_hdr",
            doc_id,
            {"to_status": "PAID", "source": "ONLINE_PAYMENT"},
            None,
            None,
        )

    # --- 4) If mismatch → RECONCILE and stop here
    if abs(collected - server_amt) > Decimal("0.01"):
        exec_sql(
            "update doc_request_hdr set request_status_id=%s, current_status_set_at=now() where doc_request_id=%s;",
            [_st("RECONCILE"), doc_id],
        )
        _log(
            "STATUS_CHANGED",
            "doc_request_hdr",
            doc_id,
            {
                "to_status": "RECONCILE",
                "reason": "COLLECTED_AMOUNT_MISMATCH",
                "server_amount": float(server_amt),
                "collected": float(collected),
            },
            None,
            None,
        )
        return  # don’t move to clerk review if reconciliation needed

    # --- 5) Move to FOR_CLERK_REVIEW (idempotent)
    try:
        st_review = _st("FOR CLERK REVIEW")
    except Exception:
        st_review = None

    if st_review and st_review != st_paid:
        exec_sql("""
          update doc_request_hdr
             set request_status_id = %s,
                 current_status_set_at = now()
           where doc_request_id = %s;
        """, [st_review, doc_id])

        _log(
            "STATUS_CHANGED",
            "doc_request_hdr",
            doc_id,
            {"to_status": "FOR CLERK REVIEW", "source": "ONLINE_PAYMENT"},
            None,
            None,
        )


def _finalize_paid(renewal_id: int, paid_dt, event_ref: str, provider_payment_id: Optional[str]):
    """
    Idempotent finalizer for renewals:
    - marks latest payment_session as PAID
    - calls process_clearance_payment_and_renew
    - advances renewal_request statuses (PAID → ISSUED)
    - optionally flags RECONCILE when collected != quote
    """
    rr = exec_one("""
      select rr.business_id, rr.period_type, rr.period_year, rr.period_quarter,
             rr.base_fee_quote, rr.total_quote
        from renewal_request rr
       where rr.renewal_request_id=%s
       limit 1;
    """, [renewal_id])
    if not rr:
        return {"ok": False, "reason": "renewal not found"}

    # flip latest session to PAID
    ps = exec_one("""
      update payment_session ps
         set status='PAID',
             paid_at=%s,
             provider_payment_id = coalesce(%s, provider_payment_id)
      from (
        select payment_session_id
          from payment_session
         where renewal_request_id=%s
         order by created_at desc
         limit 1
      ) x
      where ps.payment_session_id = x.payment_session_id
      returning ps.payment_session_id, ps.amount;
    """, [paid_dt, provider_payment_id, renewal_id])

    if ps:
        _log(
            "PAYMENT_SESSION_PAID",
            "payment_session",
            ps["payment_session_id"],
            {
                "renewal_request_id": renewal_id,
                "provider_payment_id": provider_payment_id,
                "paid_at": str(paid_dt),
                "source": "ONLINE_PAYMENT",
            },
            None,
            None,
        )

    # issue clearance (offense logic happens inside the function using paid_dt)
    res = exec_one("""
      select process_clearance_payment_and_renew(
        %s,%s,%s,%s,%s,%s,%s,%s,%s
      ) as clearance_rec_id;
    """, [
      rr["business_id"],
      rr["period_type"],
      rr["period_year"],
      paid_dt.date(),
      f"PM-{event_ref}",
      float(rr["base_fee_quote"]),
      settings.STAFF_SYSTEM_ID,  # function expects a creator id
      rr["period_quarter"],
      None
    ])
    new_rec_id = res["clearance_rec_id"]

    # move statuses: PAID → ISSUED
    exec_sql("update renewal_request set request_status_id=%s where renewal_request_id=%s;",
             [_st("PAID"), renewal_id])
    _log(
        "STATUS_CHANGED",
        "renewal_request",
        renewal_id,
        {"to_status": "PAID", "source": "ONLINE_PAYMENT"},
        None,
        None,
    )

    exec_sql("""
      update renewal_request
         set request_status_id=%s,
             paid_on=%s,
             clearance_rec_id=%s
       where renewal_request_id=%s;
    """, [_st("ISSUED"), paid_dt, new_rec_id, renewal_id])

    _log(
        "STATUS_CHANGED",
        "renewal_request",
        renewal_id,
        {"to_status": "ISSUED", "clearance_rec_id": new_rec_id, "source": "ONLINE_PAYMENT"},
        None,
        None,
    )

    # optional reconcile if mismatch
    paid_amount = exec_one("""
        select amount from payment_session
         where renewal_request_id=%s
         order by created_at desc limit 1;
    """, [renewal_id])["amount"]
    if abs(float(paid_amount) - float(rr["total_quote"])) > 0.01:
        exec_sql("update renewal_request set request_status_id=%s where renewal_request_id=%s;",
                 [_st("RECONCILE"), renewal_id])
        _log(
            "STATUS_CHANGED",
            "renewal_request",
            renewal_id,
            {
                "to_status": "RECONCILE",
                "reason": "COLLECTED_AMOUNT_MISMATCH",
                "server_amount": float(rr["total_quote"]),
                "collected": float(paid_amount),
            },
            None,
            None,
        )

    # explicit payment accepted log for renewals
    _log(
        "PAYMENT_ACCEPTED",
        "renewal_request",
        renewal_id,
        {
            "clearance_rec_id": new_rec_id,
            "amount_paid": float(paid_amount),
            "source": "ONLINE_PAYMENT",
            "or_number": f"PM-{event_ref}"
        },
        None,
        None,
    )

    return {"ok": True, "clearance_rec_id": new_rec_id}


# ============================ 1) start checkout =============================

@csrf_exempt
def start_checkout(request, renewal_id: int):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    # authoritative renewal row
    rr = exec_one("""
      select rr.renewal_request_id, rr.business_id,
             rr.period_type, rr.period_year, rr.period_quarter,
             rr.base_fee_quote, rr.surcharge_quote, rr.total_quote,
             (select request_status_id from v_req_status
               where canonical_name='PAID' limit 1) as st_pay_init
        from renewal_request rr
       where rr.renewal_request_id=%s
       limit 1;
    """, [renewal_id])
    if not rr:
        return JsonResponse({"error": "renewal not found"}, status=404)

    amount_total = Decimal(rr["total_quote"] or 0)
    if amount_total <= 0:
        return JsonResponse({"error": "invalid quoted amount"}, status=400)

    body = json.loads(request.body or "{}")

    # success/cancel URLs (default to your hosted page)
    success_url = body.get("success_url") or request.build_absolute_uri(f"/payments/success?renewal_id={renewal_id}")
    cancel_url = body.get("cancel_url", request.build_absolute_uri("/payments/success?canceled=1"))

    cents = int(round(amount_total * 100))

    # PayMongo checkout
    pm_payload = {
      "data": {
        "attributes": {
          "cancel_url":  cancel_url,
          "success_url": success_url,
          "payment_method_types": ["gcash"],
          "line_items": [{
            "name":        f"Business Clearance Renewal #{renewal_id}",
            "description": f"Business ID {rr['business_id']}",
            "amount":      cents,
            "currency":    "PHP",
            "quantity":    1
          }],
          "metadata": {
            "renewal_request_id": str(renewal_id)
          }
        }
      }
    }

    resp = requests.post(
        "https://api.paymongo.com/v1/checkout_sessions",
        headers=paymongo_auth_header(),
        data=json.dumps(pm_payload),
        timeout=30
    )
    j = resp.json()
    if resp.status_code >= 400:
        return JsonResponse(j, status=resp.status_code)

    chksn_id     = j["data"]["id"]
    checkout_url = j["data"]["attributes"]["checkout_url"]

    # record pending session
    exec_sql("""
      insert into payment_session(
        gateway, method, provider_session_id, status, amount, currency,
        checkout_url, success_url, cancel_url,
        renewal_request_id, business_id, metadata
      )
      values ('PAYMONGO','GCASH', %s, 'PENDING', %s, 'PHP',
              %s, %s, %s,
              %s, %s, %s::jsonb);
    """, [
        chksn_id, float(amount_total), checkout_url, success_url, cancel_url,
        renewal_id, rr["business_id"], json.dumps(pm_payload["data"]["attributes"]["metadata"])
    ])

    # timeline: checkout session created (SYSTEM performer)
    _log(
        "CHECKOUT_SESSION_CREATED",
        "payment_session",
        0,
        {
            "renewal_request_id": renewal_id,
            "provider_session_id": chksn_id,
            "checkout_url": checkout_url,
        },
        None,
        None,
    )

    # move renewal to PAYMENT_INITIATED (your mapping currently points to 'PAID')
    exec_sql("update renewal_request set request_status_id=%s where renewal_request_id=%s;",
             [rr["st_pay_init"], renewal_id])

    _log(
        "PAYMENT_INITIATED",
        "renewal_request",
        renewal_id,
        {"provider_session_id": chksn_id},
        None,
        None,
    )

    return JsonResponse({"checkout_url": checkout_url, "provider_session_id": chksn_id})


# ========================= 2) webhook (source of truth) =====================

@csrf_exempt
def paymongo_webhook(request):
    """
    PayMongo webhook receiver.
    - In DEV (or if signature invalid), we log and return 200 to stop retries.
    - In PROD, we verify signature; if invalid we 200 but do NOT process.
    """
    sig = request.headers.get("Paymongo-Signature", "")
    raw = request.body

    dev_mode = bool(getattr(settings, "PAYMENTS_DEV_BYPASS", False))
    verified = True

    if not dev_mode:
        try:
            verified = verify_paymongo_signature(raw, sig)
        except Exception:
            verified = False

    # Parse JSON once
    try:
        ev = json.loads(raw.decode("utf-8"))
    except Exception:
        return HttpResponse(status=200)

    # Always log the event (idempotent insert)
    typ  = ev.get("data", {}).get("attributes", {}).get("type") or ev.get("type")
    evid = ev.get("data", {}).get("id") or ev.get("id")
    try:
        exec_sql("""
          insert into payment_webhook_event(event_id, event_type, signature, verified, payload)
          values (%s,%s,%s,%s,%s::jsonb)
          on conflict (event_id) do nothing;
        """, [evid, typ, sig, bool(verified), json.dumps(ev)])
    except Exception:
        pass

    if not verified:
        return HttpResponse(status=200)

    # -------- verified: process below --------
    attrs   = ev.get("data", {}).get("attributes", {})
    inner   = attrs.get("data", ev.get("data") or {})
    iattrs  = inner.get("attributes", {})
    meta    = iattrs.get("metadata", {}) or inner.get("metadata", {}) or {}

    epoch   = attrs.get("created_at") or int(datetime.now().timestamp())
    paid_dt = datetime.fromtimestamp(epoch, tz=ZoneInfo("Asia/Manila"))

    if typ in ("checkout_session.payment.paid", "payment.paid"):
        provider_payment_id = inner.get("id") or attrs.get("payment_id")

        _log(
            "WEBHOOK_RECEIVED",
            "payment_webhook_event",
            0,
            {"event_id": evid, "event_type": typ, "provider_payment_id": provider_payment_id, "meta": meta},
            None,
            None,
        )

        if "renewal_request_id" in meta:
            _finalize_paid(int(meta["renewal_request_id"]), paid_dt, evid, provider_payment_id)
        elif "doc_request_id" in meta:
            _finalize_doc_paid(int(meta["doc_request_id"]), paid_dt, evid, provider_payment_id)

    elif typ == "payment.failed":
        try:
            exec_sql("""
              update payment_session ps
                 set status='FAILED', raw_provider=%s::jsonb
              from (
                select payment_session_id
                  from payment_session
                 order by created_at desc limit 1
              ) x
              where ps.payment_session_id = x.payment_session_id;
            """, [json.dumps(ev)])
        except Exception:
            pass
        _log(
            "PAYMENT_FAILED",
            "payment_session",
            0,
            {"event_id": evid, "payload": ev},
            None,
            None,
        )

    elif typ in ("payment.refund.updated", "payment.refunded"):
        try:
            pay_id = ev.get("data", {}).get("id")
            exec_sql("""
              update payment_session
                 set refund_status='SUCCEEDED', refund_settled_at=now(), raw_provider=%s::jsonb
               where provider_payment_id=%s;
            """, [json.dumps(ev), pay_id])
        except Exception:
            pass
        _log(
            "REFUND_SUCCEEDED",
            "payment_session",
            0,
            {"event_id": evid, "payload": ev},
            None,
            None,
        )

    return HttpResponse(status=200)


# ====================== 3) status (for polling / UI) ========================

@csrf_exempt
def renewal_status(request, renewal_id: int):
    row = exec_one("""
      select rr.renewal_request_id,
             rr.clearance_rec_id,
             coalesce(v.canonical_name, 'UNKNOWN') as status
        from renewal_request rr
        left join v_req_status v on v.request_status_id = rr.request_status_id
       where rr.renewal_request_id = %s
       limit 1;
    """, [renewal_id])

    if not row:
        return JsonResponse({"error": "not found"}, status=404)

    return JsonResponse({
        "renewal_request_id": row["renewal_request_id"],
        "status": row["status"],
        "clearance_rec_id": row["clearance_rec_id"],
    })


# ================= 4) decline & (real or simulated) refund ==================

@csrf_exempt
def decline_and_refund(request, renewal_id: int):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    if not _check_api_key(request):
        return JsonResponse({"error": "unauthorized"}, status=401)

    dev_bypass = settings.PAYMENTS_DEV_BYPASS or request.GET.get("dev") == "1"
    data   = json.loads(request.body or "{}")
    reason = data.get("reason", "Declined by Treasurer")

    # mark DECLINED
    exec_sql("update renewal_request set request_status_id=%s where renewal_request_id=%s;",
             [_st("DECLINED"), renewal_id])
    _log(
        "STATUS_CHANGED",
        "renewal_request",
        renewal_id,
        {"to_status": "DECLINED", "reason": reason},
        None,
        None,
    )

    # latest PAID session (if any)
    ps = exec_one("""
      select payment_session_id, provider_payment_id, amount
        from payment_session
       where renewal_request_id=%s and status='PAID'
       order by paid_at desc
       limit 1;
    """, [renewal_id])

    if not ps or not ps["provider_payment_id"]:
        return JsonResponse({"status": "DECLINED_NO_PAYMENT"}, status=200)

    if dev_bypass:
        # simulate immediate refund in dev/demo
        exec_sql("""
          update payment_session
             set refund_status='SUCCEEDED',
                 refund_amount=%s,
                 refund_reason=%s,
                 refund_settled_at=now()
           where payment_session_id=%s;
        """, [ps["amount"], reason, ps["payment_session_id"]])

        _log(
            "REFUND_SIMULATED",
            "payment_session",
            ps["payment_session_id"],
            {"renewal_request_id": renewal_id, "amount": float(ps["amount"]), "reason": reason},
            None,
            None,
        )

        exec_sql("update renewal_request set request_status_id=%s where renewal_request_id=%s;",
                 [_st("REFUND_PENDING"), renewal_id])

        _log(
            "STATUS_CHANGED",
            "renewal_request",
            renewal_id,
            {"to_status": "REFUND_PENDING", "reason": reason},
            None,
            None,
        )

        return JsonResponse({"status": "REFUND_SIMULATED"}, status=200)

    # real PayMongo refund
    payload = {
      "data": {"attributes": {
        "amount":     int(round(float(ps["amount"]) * 100)),
        "payment_id": ps["provider_payment_id"],
        "reason":     "requested_by_merchant",
        "notes":      reason
      }}
    }
    r = requests.post("https://api.paymongo.com/v1/refunds",
                      headers=paymongo_auth_header(),
                      data=json.dumps(payload), timeout=30)
    resp = r.json()

    exec_sql("""
      update payment_session
         set refund_status='PENDING',
             refund_id = %s,
             refund_amount = %s,
             refund_reason = %s,
             refund_requested_at = now()
       where payment_session_id=%s;
    """, [resp.get("data",{}).get("id"), ps["amount"], reason, ps["payment_session_id"]])

    _log(
        "REFUND_REQUESTED",
        "payment_session",
        ps["payment_session_id"],
        {"renewal_request_id": renewal_id, "payload": resp, "reason": reason},
        None,
        None,
    )

    exec_sql("update renewal_request set request_status_id=%s where renewal_request_id=%s;",
             [_st("REFUND_PENDING"), renewal_id])

    _log(
        "STATUS_CHANGED",
        "renewal_request",
        renewal_id,
        {"to_status": "REFUND_PENDING", "reason": reason},
        None,
        None,
    )

    return JsonResponse({"status": "REFUND_PENDING", "provider_refund": resp}, status=200)


# ============= 5) confirm after redirect (success page calls this) ==========

@csrf_exempt
def confirm_after_redirect(request, renewal_id: int):
    """
    Fallback finalizer. In DEV it immediately finalizes.
    In LIVE it queries the Checkout Session and finalizes only if paid.
    Safe to call multiple times.
    """
    dev_bypass = settings.PAYMENTS_DEV_BYPASS or request.GET.get("dev") == "1"

    ps = exec_one("""
      select payment_session_id, provider_session_id, status
        from payment_session
       where renewal_request_id=%s
       order by created_at desc
       limit 1;
    """, [renewal_id])
    if not ps:
        return JsonResponse({"error": "no_session"}, status=404)

    # already paid?
    if ps["status"] == "PAID":
        row = exec_one("""
          select rr.clearance_rec_id,
                 coalesce(v.canonical_name,'UNKNOWN') as status
            from renewal_request rr
            left join v_req_status v on v.request_status_id=rr.request_status_id
           where rr.renewal_request_id=%s
           limit 1;
        """, [renewal_id])
        return JsonResponse({"status": row["status"], "clearance_rec_id": row["clearance_rec_id"]})

    # DEV: finalize without contacting PayMongo
    if dev_bypass:
        paid_dt = datetime.now(tz=ZoneInfo("Asia/Manila"))
        done = _finalize_paid(renewal_id, paid_dt, f"DEV-{ps['provider_session_id']}", "DEV_PAYMENT")
        if not done["ok"]:
            return JsonResponse({"error": done.get("reason", "finalize_failed")}, status=400)
        row = exec_one("""
          select rr.clearance_rec_id,
                 coalesce(v.canonical_name,'UNKNOWN') as status
            from renewal_request rr
            left join v_req_status v on v.request_status_id=rr.request_status_id
           where rr.renewal_request_id=%s
           limit 1;
        """, [renewal_id])
        return JsonResponse({"status": row["status"], "clearance_rec_id": row["clearance_rec_id"]})

    # LIVE: check the checkout_session
    cs_id = ps["provider_session_id"]
    r = requests.get(f"https://api.paymongo.com/v1/checkout_sessions/{cs_id}",
                     headers=paymongo_auth_header(), timeout=20)
    j = r.json()
    if r.status_code >= 400:
        return JsonResponse({"status": "PENDING", "provider_response": j}, status=200)

    attrs = j.get("data", {}).get("attributes", {})
    status = (attrs.get("status") or attrs.get("payment_status") or "").lower()

    paid = (status == "paid")
    provider_payment_id = None

    # some responses include a payments list
    payments = attrs.get("payments") or []
    if isinstance(payments, list):
        for p in payments:
            if isinstance(p, dict) and p.get("status", "").lower() in ("paid", "succeeded", "successful"):
                paid = True
                provider_payment_id = p.get("id") or p.get("payment_id")
                break

    if not paid:
        return JsonResponse({"status": "PENDING", "provider_status": status}, status=200)

    paid_dt = datetime.now(tz=ZoneInfo("Asia/Manila"))
    done = _finalize_paid(renewal_id, paid_dt, cs_id, provider_payment_id)
    if not done["ok"]:
        return JsonResponse({"error": done.get("reason", "finalize_failed")}, status=400)

    row = exec_one("""
      select rr.clearance_rec_id,
             coalesce(v.canonical_name,'UNKNOWN') as status
        from renewal_request rr
        left join v_req_status v on v.request_status_id=rr.request_status_id
       where rr.renewal_request_id=%s
       limit 1;
    """, [renewal_id])

    return JsonResponse({"status": row["status"], "clearance_rec_id": row["clearance_rec_id"]})


# --- DOC REQUEST: confirm after redirect (DEV bypass supported) -------------
@csrf_exempt
def confirm_doc_after_redirect(request, doc_id: int):
    """
    Same behavior as renewals: in DEV it immediately finalizes,
    in LIVE it queries the PayMongo checkout session and finalizes only if paid.
    Safe to call multiple times.
    """
    dev_bypass = settings.PAYMENTS_DEV_BYPASS or request.GET.get("dev") == "1"

    ps = exec_one("""
      select payment_session_id, provider_session_id, status
        from payment_session
       where doc_request_id=%s
       order by created_at desc
       limit 1;
    """, [doc_id])
    if not ps:
        return JsonResponse({"error": "no_session"}, status=404)

    # already paid?
    if ps["status"] == "PAID":
        row = exec_one("""
          select coalesce(v.canonical_name,'UNKNOWN') as status
            from doc_request_hdr h
            left join v_req_status v on v.request_status_id = h.request_status_id
           where h.doc_request_id = %s
           limit 1;
        """, [doc_id])
        return JsonResponse({"status": row["status"]})

    # DEV: finalize without contacting PayMongo
    if dev_bypass:
        paid_dt = datetime.now(tz=ZoneInfo("Asia/Manila"))
        _finalize_doc_paid(doc_id, paid_dt, f"DEV-{ps['provider_session_id']}", "DEV_PAYMENT")
        row = exec_one("""
          select coalesce(v.canonical_name,'UNKNOWN') as status
            from doc_request_hdr h
            left join v_req_status v on v.request_status_id = h.request_status_id
           where h.doc_request_id = %s
           limit 1;
        """, [doc_id])
        return JsonResponse({"status": row["status"]})

    # LIVE: check the checkout_session
    cs_id = ps["provider_session_id"]
    r = requests.get(f"https://api.paymongo.com/v1/checkout_sessions/{cs_id}",
                     headers=paymongo_auth_header(), timeout=20)
    j = r.json()
    if r.status_code >= 400:
        return JsonResponse({"status": "PENDING", "provider_response": j}, status=200)

    attrs = j.get("data", {}).get("attributes", {})
    status = (attrs.get("status") or attrs.get("payment_status") or "").lower()

    paid = (status == "paid")
    provider_payment_id = None

    payments = attrs.get("payments") or []
    if isinstance(payments, list):
        for p in payments:
            if isinstance(p, dict) and p.get("status", "").lower() in ("paid", "succeeded", "successful"):
                paid = True
                provider_payment_id = p.get("id") or p.get("payment_id")
                break

    if not paid:
        return JsonResponse({"status": "PENDING", "provider_status": status}, status=200)

    paid_dt = datetime.now(tz=ZoneInfo("Asia/Manila"))
    _finalize_doc_paid(doc_id, paid_dt, cs_id, provider_payment_id)

    row = exec_one("""
      select coalesce(v.canonical_name,'UNKNOWN') as status
        from doc_request_hdr h
        left join v_req_status v on v.request_status_id = h.request_status_id
       where h.doc_request_id = %s
       limit 1;
    """, [doc_id])
    return JsonResponse({"status": row["status"]})


# =========================== 6) success page ================================

@require_GET
def success(request):
    """
    Unified success page for both Renewal and Document flows.

    Accepts:
      ?renewal_id=123 OR ?doc_id=456
      &return_to=<deep-link generated by the app>
    """
    renewal_id_raw = request.GET.get("renewal_id")
    doc_id_raw     = request.GET.get("doc_id")
    if not renewal_id_raw and not doc_id_raw:
        return HttpResponseBadRequest("Missing renewal_id or doc_id")

    dev_bypass = settings.PAYMENTS_DEV_BYPASS or request.GET.get("dev") == "1"
    status = "PENDING"
    clearance_rec_id = None

    # sanitize/prepare deep link
    scheme = getattr(settings, "APP_SCHEME", "barug")
    default_link = None
    if renewal_id_raw:
        default_link = f"{scheme}://renewal?id={renewal_id_raw}"
    elif doc_id_raw:
        default_link = f"{scheme}://receipt?id={doc_id_raw}"

    return_to = _sanitize_return_to(unquote(request.GET.get("return_to") or "")) or default_link

    # --- Try to finalize server-side (safe/idempotent) ---
    try:
        if renewal_id_raw:
            renewal_id = int(renewal_id_raw)

            ps = exec_one("""
              select payment_session_id, provider_session_id, status
                from payment_session
               where renewal_request_id=%s
               order by created_at desc
               limit 1;
            """, [renewal_id])

            if ps and ps["status"] == "PAID":
                status = "PAID"
                row = exec_one("""
                  select rr.clearance_rec_id from renewal_request rr where rr.renewal_request_id=%s limit 1;
                """, [renewal_id])
                clearance_rec_id = (row or {}).get("clearance_rec_id")

            else:
                if dev_bypass and ps:
                    paid_dt = datetime.now(tz=ZoneInfo("Asia/Manila"))
                    done = _finalize_paid(renewal_id, paid_dt, f"DEV-{ps['provider_session_id']}", "DEV_PAYMENT")
                    status = "PAID" if done.get("ok") else "PENDING"
                    clearance_rec_id = done.get("clearance_rec_id")
                elif ps:
                    cs_id = ps["provider_session_id"]
                    r = requests.get(f"https://api.paymongo.com/v1/checkout_sessions/{cs_id}",
                                     headers=paymongo_auth_header(), timeout=20)
                    j = r.json()
                    attrs = j.get("data", {}).get("attributes", {}) if r.status_code < 400 else {}
                    pst = (attrs.get("status") or attrs.get("payment_status") or "").lower()
                    paid = (pst == "paid")
                    payments = attrs.get("payments") or []
                    if isinstance(payments, list):
                        for p in payments:
                            if isinstance(p, dict) and p.get("status", "").lower() in ("paid", "succeeded", "successful"):
                                paid = True
                                provider_payment_id = p.get("id") or p.get("payment_id")
                                break
                        else:
                            provider_payment_id = None
                    else:
                        provider_payment_id = None
                    if paid:
                        paid_dt = datetime.now(tz=ZoneInfo("Asia/Manila"))
                        done = _finalize_paid(renewal_id, paid_dt, cs_id, provider_payment_id)
                        status = "PAID" if done.get("ok") else "PENDING"
                        clearance_rec_id = done.get("clearance_rec_id")

        elif doc_id_raw:
            doc_id = int(doc_id_raw)

            ps = exec_one("""
              select payment_session_id, provider_session_id, status
                from payment_session
               where doc_request_id=%s
               order by created_at desc
               limit 1;
            """, [doc_id])

            if ps and ps["status"] == "PAID":
                status = "PAID"
            else:
                if dev_bypass and ps:
                    paid_dt = datetime.now(tz=ZoneInfo("Asia/Manila"))
                    _finalize_doc_paid(doc_id, paid_dt, f"DEV-{ps['provider_session_id']}", "DEV_PAYMENT")
                    status = "PAID"
                elif ps:
                    cs_id = ps["provider_session_id"]
                    r = requests.get(f"https://api.paymongo.com/v1/checkout_sessions/{cs_id}",
                                     headers=paymongo_auth_header(), timeout=20)
                    j = r.json()
                    attrs = j.get("data", {}).get("attributes", {}) if r.status_code < 400 else {}
                    pst = (attrs.get("status") or attrs.get("payment_status") or "").lower()
                    paid = (pst == "paid")
                    payments = attrs.get("payments") or []
                    provider_payment_id = None
                    if isinstance(payments, list):
                        for p in payments:
                            if isinstance(p, dict) and p.get("status", "").lower() in ("paid", "succeeded", "successful"):
                                paid = True
                                provider_payment_id = p.get("id") or p.get("payment_id")
                                break
                    if paid:
                        paid_dt = datetime.now(tz=ZoneInfo("Asia/Manila"))
                        _finalize_doc_paid(doc_id, paid_dt, cs_id, provider_payment_id)
                        status = "PAID"
    except Exception:
        # keep status as PENDING on error
        pass

    # --- Render minimal page that auto-bounces back if PAID ---
    success_text = (
        f"Payment recorded. Clearance Ref: {clearance_rec_id}" if clearance_rec_id
        else "Payment recorded. Your request is now paid / for clerk review."
    )
    instant_meta = (f'<meta http-equiv="refresh" content="0; url={return_to}">' if (status == "PAID" and return_to) else "")
    instant_js = (
        f"""
        <script>
          (function(){{
            var target = "{(return_to or '').replace('"','%22')}";
            if (!target) return;
            try {{ window.location.replace(target); }} catch(e) {{}}
            setTimeout(function(){{ try{{ window.location.href = target; }}catch(e){{}} }}, 200);
            setTimeout(function(){{ try{{ window.location.assign(target); }}catch(e){{}} }}, 800);
          }})();
        </script>
        """ if (status == "PAID" and return_to) else ""
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Finalizing your payment…</title>
  {instant_meta}
  {instant_js}
  <style>
    :root{{--brand:#310101;--ink:#111827;--muted:#6b7280;--ok-bg:#ecfdf5;--ok-fg:#065f46;--ok-br:#86efac;--card:#ffffff;--page:#fff7f5;--border:#e5e7eb}}
    html,body{{margin:0;height:100%;background:var(--page);font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,"Helvetica Neue",Arial}}
    .wrap{{min-height:100%;display:flex;align-items:flex-start;justify-content:center;padding:24px}}
    .card{{width:100%;max-width:720px;background:var(--card);border:1px solid var(--border);border-radius:16px;padding:22px 18px 20px}}
    h1{{margin:0 0 6px;font-size:28px;line-height:1.2;color:var(--ink)}}
    p{{color:var(--muted);margin:6px 0 0}}
    .status{{margin-top:12px;font-weight:700;color:var(--ink)}}
    .alert-ok{{margin-top:14px;border:1px solid var(--ok-br);background:var(--ok-bg);color:var(--ok-fg);border-radius:12px;padding:12px 14px}}
    .btn{{display:inline-block;margin-top:16px;padding:12px 16px;border-radius:12px;text-decoration:none;background:#eef2ff;color:#3730a3;border:1px solid #c7d2fe;font-weight:700}}
    .hint{{color:var(--muted);font-size:12px;margin-top:8px}}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Thanks! We’re finalizing your payment…</h1>
      <p>This page will refresh or return to the app automatically.</p>
      <div class="status">Status: <strong>{status}</strong></div>
      {"<div class='alert-ok'>" + success_text + "</div>" if status == "PAID" else ""}
      {"<a class='btn' href='" + return_to + "'>Go back and check the receipt</a>" if return_to else ""}
      {"<div class='hint'>If it doesn’t return automatically, tap the button above.</div>" if status == "PAID" and return_to else ""}
    </div>
  </div>
</body>
</html>"""
    return HttpResponse(html)


# --- DOC REQUEST: start checkout (mirrors renewal start) ---------------------

@csrf_exempt
def start_doc_checkout(request, doc_id: int):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    body = json.loads(request.body or "{}")

    # 0) Reuse a recent pending/paid session to avoid duplicate "PAYMENT_INITIATED"
    reuse = exec_one("""
      select provider_session_id, checkout_url, status, created_at
        from payment_session
       where doc_request_id=%s
       order by created_at desc
       limit 1
    """, [doc_id])
    if reuse and reuse["status"] in ("PENDING", "PAID"):
        return JsonResponse({
            "checkout_url": reuse["checkout_url"],
            "provider_session_id": reuse["provider_session_id"]
        })

    # 1) Authoritative server amount (for later comparison)
    srv = exec_one("select _doc_request_amount(%s) as amount_due;", [doc_id])
    if not srv or srv["amount_due"] is None:
        return JsonResponse({"error": "doc request not found"}, status=404)
    server_amount = Decimal(srv["amount_due"] or 0)

    # 2) Use client amount if flag allows; else use server amount
    use_client = bool(getattr(settings, "PAYMENTS_TRUST_CLIENT_DOC_AMOUNT", False))
    amount_total = server_amount
    if use_client and ("amount" in body):
        try:
            amount_total = Decimal(str(body["amount"]))
        except Exception:
            return JsonResponse({"error": "invalid amount"}, status=400)

    if amount_total <= 0:
        return JsonResponse({"error": "invalid quoted amount"}, status=400)

    success_url = body.get("success_url") or request.build_absolute_uri(f"/payments/success?doc_id={doc_id}")
    cancel_url  = body.get("cancel_url")  or request.build_absolute_uri("/payments/success?canceled=1")
    cents = int(round(amount_total * 100))

    pm_payload = {
      "data": {"attributes": {
        "cancel_url":  cancel_url,
        "success_url": success_url,
        "payment_method_types": ["gcash"],
        "line_items": [{
          "name":        f"Barangay Document Request #{doc_id}",
          "description": f"Doc Request #{doc_id}",
          "amount":      cents,
          "currency":    "PHP",
          "quantity":    1
        }],
        "metadata": {
          "doc_request_id": str(doc_id)
        }
      }}
    }

    resp = requests.post(
        "https://api.paymongo.com/v1/checkout_sessions",
        headers=paymongo_auth_header(),
        data=json.dumps(pm_payload),
        timeout=30
    )
    j = resp.json()
    if resp.status_code >= 400:
        return JsonResponse(j, status=resp.status_code)

    chksn_id     = j["data"]["id"]
    checkout_url = j["data"]["attributes"]["checkout_url"]

    # Store intended amount + original client payload for audit
    exec_sql("""
      insert into payment_session(
        gateway, method, provider_session_id, status, amount, currency,
        checkout_url, success_url, cancel_url,
        doc_request_id, metadata
      ) values (
        'PAYMONGO','GCASH', %s, 'PENDING', %s, 'PHP',
        %s, %s, %s,
        %s, %s::jsonb
      );
    """, [
        chksn_id, float(amount_total), checkout_url, success_url, cancel_url,
        doc_id, json.dumps({"client_payload": body, "metadata": pm_payload["data"]["attributes"]["metadata"]})
    ])

    _log(
        "CHECKOUT_SESSION_CREATED",
        "payment_session",
        0,
        {
            "doc_request_id": doc_id,
            "provider_session_id": chksn_id,
            "checkout_url": checkout_url,
        },
        None,
        None,
    )

    # Prefer a non-PAID prepayment status if you have one
    try:
        st_init = _st("PAYMENT_INITIATED")
    except Exception:
        st_init = None

    if st_init:
        exec_sql(
            "update doc_request_hdr set request_status_id=%s where doc_request_id=%s;",
            [st_init, doc_id]
        )

    _log(
        "PAYMENT_INITIATED",
        "doc_request_hdr",
        doc_id,
        {"provider_session_id": chksn_id},
        None,
        None,
    )

    return JsonResponse({"checkout_url": checkout_url, "provider_session_id": chksn_id})


# --- DOC REQUEST: status (simple poll endpoint) ------------------------------

@csrf_exempt
def doc_status(request, doc_id: int):
    row = exec_one("""
      select h.doc_request_id,
             coalesce(v.canonical_name,'UNKNOWN') as status
        from doc_request_hdr h
        left join v_req_status v on v.request_status_id=h.request_status_id
       where h.doc_request_id=%s
       limit 1;
    """, [doc_id])
    if not row:
        return JsonResponse({"error":"not found"}, status=404)
    return JsonResponse({"doc_request_id": row["doc_request_id"], "status": row["status"]})
