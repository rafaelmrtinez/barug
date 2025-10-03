# payments/views.py
import json
import requests
from decimal import Decimal
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt

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


def _finalize_paid(renewal_id: int, paid_dt, event_ref: str, provider_payment_id: str | None):
    """
    Idempotent finalizer:
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
    exec_sql("""
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
      where ps.payment_session_id = x.payment_session_id;
    """, [paid_dt, provider_payment_id, renewal_id])

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
      settings.STAFF_SYSTEM_ID,
      rr["period_quarter"],
      None
    ])
    new_rec_id = res["clearance_rec_id"]

    # move statuses: PAID → ISSUED
    exec_sql("update renewal_request set request_status_id=%s where renewal_request_id=%s;",
             [_st("PAID"), renewal_id])
    exec_sql("""
      update renewal_request
         set request_status_id=%s,
             paid_on=%s,
             clearance_rec_id=%s
       where renewal_request_id=%s;
    """, [_st("ISSUED"), paid_dt, new_rec_id, renewal_id])

    # optional reconcile if mismatch
    paid_amount = exec_one("""
        select amount from payment_session
         where renewal_request_id=%s
         order by created_at desc limit 1;
    """, [renewal_id])["amount"]
    if abs(float(paid_amount) - float(rr["total_quote"])) > 0.01:
        exec_sql("update renewal_request set request_status_id=%s where renewal_request_id=%s;",
                 [_st("RECONCILE"), renewal_id])

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
    if "success_url" in body:
        success_url = body["success_url"]
    else:
        success_url = request.build_absolute_uri(f"/payments/success?renewal_id={renewal_id}")
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

    # move renewal to PAYMENT_INITIATED
    exec_sql("update renewal_request set request_status_id=%s where renewal_request_id=%s;",
             [rr["st_pay_init"], renewal_id])

    return JsonResponse({"checkout_url": checkout_url, "provider_session_id": chksn_id})


# ========================= 2) webhook (source of truth) =====================

@csrf_exempt
def paymongo_webhook(request):
    sig = request.headers.get("Paymongo-Signature", "")
    raw = request.body
    if not verify_paymongo_signature(raw, sig):
        return HttpResponseBadRequest("Invalid signature")

    ev   = json.loads(raw.decode("utf-8"))
    typ  = ev.get("data",{}).get("attributes",{}).get("type") or ev.get("type")
    evid = ev.get("data",{}).get("id") or ev.get("id")

    exec_sql("""
      insert into payment_webhook_event(event_id, event_type, signature, verified, payload)
      values (%s,%s,%s,true,%s::jsonb)
      on conflict (event_id) do nothing;
    """, [evid, typ, sig, json.dumps(ev)])

    attrs   = ev.get("data",{}).get("attributes",{})
    inner   = attrs.get("data", ev.get("data") or {})
    iattrs  = inner.get("attributes", {})
    meta    = iattrs.get("metadata", {}) or inner.get("metadata", {}) or {}

    epoch   = attrs.get("created_at") or int(datetime.now().timestamp())
    paid_dt = datetime.fromtimestamp(epoch, tz=ZoneInfo("Asia/Manila"))

    if typ in ("checkout_session.payment.paid", "payment.paid"):
        provider_payment_id = inner.get("id") or attrs.get("payment_id")
        if "renewal_request_id" in meta:
            _finalize_paid(int(meta["renewal_request_id"]), paid_dt, evid, provider_payment_id)
        elif "doc_request_id" in meta:
            _finalize_doc_paid(int(meta["doc_request_id"]), paid_dt, evid, provider_payment_id)


    elif typ == "payment.failed":
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

    elif typ in ("payment.refund.updated", "payment.refunded"):
        pay_id = ev.get("data",{}).get("id")
        exec_sql("""
          update payment_session
             set refund_status='SUCCEEDED', refund_settled_at=now(), raw_provider=%s::jsonb
           where provider_payment_id=%s;
        """, [json.dumps(ev), pay_id])

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
        exec_sql("update renewal_request set request_status_id=%s where renewal_request_id=%s;",
                 [_st("REFUND_PENDING"), renewal_id])  # or a custom DEV_REFUNDED if you prefer
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

    exec_sql("update renewal_request set request_status_id=%s where renewal_request_id=%s;",
             [_st("REFUND_PENDING"), renewal_id])

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
# payments/views.py  (replace the whole success_page function)

# payments/views.py
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest
from urllib.parse import unquote

def success_page(request):
    """
    Unified success page for both Renewal and Document flows.
    Accepts ?renewal_id=123 OR ?doc_id=456.
    Optional ?return_to=<deep-link> (generated by the app).
    Stops polling at terminal states and attempts to open the app once.
    """
    renewal_id = request.GET.get("renewal_id")
    doc_id     = request.GET.get("doc_id")
    if not renewal_id and not doc_id:
        return HttpResponseBadRequest("Missing renewal_id or doc_id")

    # Deep-link scheme fallback if the app didn't pass return_to
    scheme = getattr(settings, "APP_SCHEME", "barug")
    default_link = f"{scheme}://renewal?id={renewal_id}" if renewal_id else f"{scheme}://receipt?id={doc_id}"
    app_link = unquote(request.GET.get("return_to") or "") or default_link

    if renewal_id:
        poll_url    = f"/payments/api/renewals/{renewal_id}/confirm"
        poll_method = "POST"
        success_msg = "Payment recorded. Clearance Ref: "
        show_clearance = True
    else:
        poll_url    = f"/payments/api/docs/{doc_id}/confirm"
        poll_method = "POST"
        success_msg = "Payment recorded. Your request is now paid / for printing."
        show_clearance = False

    html = f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width,initial-scale=1"/>
    <title>Payment Success</title>
    <style>
      body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; padding: 24px; background:#fff7f5; }}
      .card {{ max-width: 720px; margin: 0 auto; border: 1px solid #e5e7eb; border-radius: 16px; padding: 20px; background:white; }}
      .ok {{ color: #065f46; background: #ecfdf5; border: 1px solid #a7f3d0; padding: 8px 12px; border-radius: 8px; display:inline-block; }}
      .muted {{ color: #6b7280; }}
      .spinner {{ width:16px;height:16px;border:2px solid #d1d5db;border-top-color:#111827;border-radius:50%;display:inline-block;animation:spin .8s linear infinite;vertical-align:middle }}
      @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
      .btn {{ display:inline-flex; gap:.5rem; align-items:center; padding:10px 14px; border-radius:10px; border:1px solid #dbe1ea; text-decoration:none; }}
      .btn-primary {{ color:#1d4ed8; background:#eef2ff; border-color:#c7d2fe; }}
      .actions {{ margin-top: 14px; display:none; }}
      h2 {{ margin: 0 0 8px 0; line-height: 1.2; }}
    </style>
  </head>
  <body>
    <div class="card">
      <h2>Thanks! We’re finalizing your payment… <span id="spin" class="spinner"></span></h2>
      <p class="muted">This page will refresh the status automatically.</p>
      <div id="status" class="muted">Checking…</div>
      <div id="result" style="margin-top:8px;"></div>
      <div id="actions" class="actions">
        <a class="btn btn-primary" id="open" href="{app_link}">Go back and check the receipt</a>
      </div>
    </div>
    <script>
      const pollUrl    = "{poll_url}";
      const pollMethod = "{poll_method}";
      const showClearance = {str(show_clearance).lower()};
      const appLink = "{app_link}".trim();
      let doneFlag = false;
      let timerId  = null;

      function stop() {{
        doneFlag = true;
        if (timerId) {{ clearTimeout(timerId); timerId = null; }}
        const sp = document.getElementById("spin");
        if (sp) sp.style.display = "none";
        const acts = document.getElementById("actions");
        if (acts) acts.style.display = "block";
      }}

      function tryOpenApp() {{
        if (!appLink) return;
        // Attempt once; browsers will show the chooser if available.
        window.location.href = appLink;
      }}

      function done(status, data) {{
        let msg = "{success_msg}";
        if (showClearance && data && data.clearance_rec_id) {{
          msg += (data.clearance_rec_id);
        }}
        document.getElementById("result").innerHTML = '<p class="ok">'+msg+'</p>';
        stop();
        // auto-attempt to open the app once
        setTimeout(tryOpenApp, 100);
      }}

      async function poll() {{
        if (doneFlag) return;
        try {{
          const r = await fetch(pollUrl, {{ method: pollMethod }});
          const j = await r.json();
          const status = (j.status || "").toUpperCase();
          document.getElementById("status").textContent = "Status: " + (status || "…");

          if (["PAID","FOR_PRINTING","ISSUED","READY_FOR_PICKUP","RELEASED"].includes(status)) {{
            done(status, j);
            return;
          }}
        }} catch (e) {{
          console.error(e);
          document.getElementById("status").textContent = "Still waiting…";
        }}
        timerId = setTimeout(poll, 1500);
      }}
      poll();
    </script>
  </body>
</html>"""
    return HttpResponse(html)


# --- DOC REQUEST: start checkout (mirrors renewal start) ---------------------
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal
import json, requests
from django.http import JsonResponse, HttpResponseBadRequest

@csrf_exempt
def start_doc_checkout(request, doc_id: int):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    body = json.loads(request.body or "{}")

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

    # Store exactly what we intend to collect (amount_total) + original client payload for audit
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

    exec_sql("update doc_request_hdr set request_status_id=%s where doc_request_id=%s;",
             [_st("PAID"), doc_id])

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

from datetime import datetime
from zoneinfo import ZoneInfo

def _payment_method_online_id():
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

def _finalize_doc_paid(doc_id: int, paid_dt, event_ref: str, provider_payment_id: str | None):
    # Mark latest session as PAID and fetch amounts
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

    collected = Decimal(str(ps["amount"] or 0))
    server    = exec_one("select _doc_request_amount(%s) as amt;", [doc_id])
    server_amt = Decimal(str((server or {}).get("amt", 0)))

    pm_id  = _payment_method_online_id()
    or_no  = _make_or_number_fallback(event_ref)
    issuer = getattr(settings, "STAFF_SYSTEM_ID", None)

    # Issue OR for the collected amount (what the gateway charged)
    exec_sql("""
      insert into official_receipt(
        or_number, issued_by_staff_id, doc_request_id, payment_method_id,
        amount_due, amount_paid, change_due
      ) values (%s, %s, %s, %s, %s, %s, 0);
    """, [or_no, issuer, doc_id, pm_id, float(collected), float(collected)])

    # Advance status (PAID or FOR_PRINTING)
    auto_fp = bool(getattr(settings, "ONLINE_PAYMENT_AUTO_ADVANCE", False))
    exec_sql("""
      update doc_request_hdr
         set request_status_id = %s,
             current_status_set_at = now()
       where doc_request_id = %s;
    """, [_st("FOR_PRINTING" if auto_fp else "PAID"), doc_id])

    # Reconcile flag if mismatch
    if abs(collected - server_amt) > Decimal("0.01"):
        exec_sql("update doc_request_hdr set request_status_id=%s where doc_request_id=%s;",
                 [_st("RECONCILE"), doc_id])
