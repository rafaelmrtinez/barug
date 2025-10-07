from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, date, timezone as dt_timezone
from typing import Any, Dict, List, Tuple
from zoneinfo import ZoneInfo

from django.utils import timezone

from authentication.supabase_client import supabase


PH_TZ = ZoneInfo("Asia/Manila")
UTC = dt_timezone.utc

# Reuse the same “wide” view you already have for request metadata
REQUESTS_VIEW = "v_doc_request_list_ex_v2"

@dataclass
class ReportRow:
    # request meta
    doc_request_id: int
    request_code: str | None
    requester: str | None
    doc_types: List[str]
    status: str | None
    request_created_at: str | None

    # OR/payment
    or_id: int | None
    or_number: str | None
    payment_method_id: int | None
    payment_method_name: str | None
    amount_due: float
    amount_paid: float
    change_due: float
    or_created_at: str  # ISO in UTC (back-compat name; sourced from issued_at)

    # derived
    balance: float

@dataclass
class ReportTotals:
    rows_count: int
    total_due: float
    total_paid: float
    total_change: float
    total_balance: float
    avg_ticket: float
    by_method: Dict[str, float]
    by_doc_type: Dict[str, float]


def _parse_date_local(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def _ph_day_bounds_utc(d: date) -> Tuple[datetime, datetime]:
    start_local = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=PH_TZ)
    end_local = start_local + timedelta(days=1) - timedelta(milliseconds=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def _calc_default_range_utc() -> Tuple[datetime, datetime]:
    """Current month in PH, returned as UTC bounds."""
    now_local = timezone.localtime(timezone.now(), PH_TZ)
    month_start_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_month = (month_start_local.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_end_local = next_month - timedelta(milliseconds=1)
    return month_start_local.astimezone(UTC), month_end_local.astimezone(UTC)


def list_payment_methods_map() -> Dict[int, str]:
    res = supabase.table("payment_method").select("payment_method_id, method_name").execute()
    out: Dict[int, str] = {}
    for r in res.data or []:
        mid = r.get("payment_method_id")
        name = (r.get("method_name") or "").strip()
        if mid is not None:
            out[int(mid)] = name
    return out


def fetch_report_rows(
    start_utc: datetime | None = None,
    end_utc: datetime | None = None,
    q: str | None = None,
    doc_type: str | None = None,
    payment_method_id: int | None = None,
) -> List[ReportRow]:
    """Pull ORs within the time window and enrich with request metadata."""
    if not start_utc or not end_utc:
        start_utc, end_utc = _calc_default_range_utc()

    # 1) Pull official receipts (money lives here)
    qb = (
        supabase.table("official_receipt")
        .select(
            "or_id, or_number, doc_request_id, amount_due, amount_paid, change_due, "
            "payment_method_id, issued_at"
        )
        .gte("issued_at", start_utc.isoformat())
        .lte("issued_at", end_utc.isoformat())
        .order("issued_at", desc=True)
        .limit(5000)
    )
    if payment_method_id:
        qb = qb.eq("payment_method_id", payment_method_id)
    if q:
        qb = qb.or_(f"or_number.ilike.%{q}%,doc_request_id.eq.{q}" if q.isdigit() else f"or_number.ilike.%{q}%")

    or_res = qb.execute()
    or_rows = list(or_res.data or [])
    if not or_rows:
        return []

    # doc_request_ids to look up
    req_ids = [r["doc_request_id"] for r in or_rows if r.get("doc_request_id") is not None]

    # 2) Pull request metadata from the view (select * to avoid unknown-column errors)
    meta_map: Dict[int, dict] = {}
    batch = 800
    for i in range(0, len(req_ids), batch):
        chunk = req_ids[i : i + batch]
        rq = (
            supabase.table(REQUESTS_VIEW)
            .select("*")
            .in_("doc_request_id", chunk)
        )
        if doc_type:
            rq = rq.contains("doc_types", [doc_type])
        mres = rq.execute()
        for row in mres.data or []:
            meta_map[int(row["doc_request_id"])] = row

    # 3) Map payment methods
    method_map = list_payment_methods_map()

    # 4) Build output rows (and apply the doc_type filter if we had to post-hoc)
    out: List[ReportRow] = []
    for o in or_rows:
        rid = int(o.get("doc_request_id") or 0)
        meta = meta_map.get(rid, {})

        # requester fallback chain (handle different view schemas)
        requester = (
            meta.get("requester_full_name")
            or meta.get("requester_name")
            or meta.get("requester")
            or meta.get("resident_full_name")
            or None
        )

        docs = list(meta.get("doc_types") or [])
        if doc_type and doc_type not in docs:
            continue  # filtered out

        amt_due = float(o.get("amount_due") or 0.0)
        amt_paid = float(o.get("amount_paid") or 0.0)
        change = float(o.get("change_due") or 0.0)
        balance = round(amt_due - amt_paid, 2)

        out.append(
            ReportRow(
                doc_request_id=rid,
                request_code=meta.get("request_code"),
                requester=requester,
                doc_types=docs,
                status=meta.get("status"),
                request_created_at=meta.get("created_at"),

                or_id=int(o.get("or_id") or 0),
                or_number=(o.get("or_number") or None),
                payment_method_id=(int(o.get("payment_method_id")) if o.get("payment_method_id") is not None else None),
                payment_method_name=method_map.get(int(o.get("payment_method_id") or 0)),
                amount_due=amt_due,
                amount_paid=amt_paid,
                change_due=change,
                or_created_at=o.get("issued_at"),  # from issued_at
                balance=balance,
            )
        )
    return out


def compute_totals(rows: List[ReportRow]) -> ReportTotals:
    total_due = sum(r.amount_due for r in rows)
    total_paid = sum(r.amount_paid for r in rows)
    total_change = sum(r.change_due for r in rows)
    total_balance = sum(r.balance for r in rows)
    avg_ticket = (total_paid / len(rows)) if rows else 0.0

    by_method: Dict[str, float] = {}
    for r in rows:
        key = r.payment_method_name or "Unknown"
        by_method[key] = by_method.get(key, 0.0) + r.amount_paid

    by_doc_type: Dict[str, float] = {}
    for r in rows:
        for d in (r.doc_types or []):
            by_doc_type[d] = by_doc_type.get(d, 0.0) + r.amount_paid

    return ReportTotals(
        rows_count=len(rows),
        total_due=round(total_due, 2),
        total_paid=round(total_paid, 2),
        total_change=round(total_change, 2),
        total_balance=round(total_balance, 2),
        avg_ticket=round(avg_ticket, 2),
        by_method=by_method,
        by_doc_type=by_doc_type,
    )


def build_financial_report_payload(
    start_date_str: str | None,
    end_date_str: str | None,
    q: str | None,
    doc_type: str | None,
    payment_method_id: int | None,
) -> Dict[str, Any]:
    # Resolve range
    sd = _parse_date_local(start_date_str)
    ed = _parse_date_local(end_date_str)
    if sd and not ed:
        ed = sd
    if not sd or not ed:
        start_utc, end_utc = _calc_default_range_utc()
    else:
        start_utc, _ = _ph_day_bounds_utc(sd)
        _, end_utc = _ph_day_bounds_utc(ed)

    rows = fetch_report_rows(start_utc, end_utc, q, doc_type, payment_method_id)
    totals = compute_totals(rows)

    # Options for filters
    methods = list_payment_methods_map()
    doc_types_all: List[str] = []
    # pull some doc types from the requests view (best-effort)
    try:
        r = (
            supabase.table(REQUESTS_VIEW)
            .select("doc_types")
            .limit(200)
            .execute()
        )
        seen = set()
        for item in r.data or []:
            for d in item.get("doc_types") or []:
                if d not in seen:
                    seen.add(d)
        doc_types_all = sorted(seen)
    except Exception:
        doc_types_all = []

    return {
        "rows": [r.__dict__ for r in rows],
        "totals": totals.__dict__,
        "filters": {
            "methods": [{"id": mid, "name": name} for mid, name in methods.items()],
            "doc_types": doc_types_all,
            "start_iso": start_utc.isoformat(),
            "end_iso": end_utc.isoformat(),
        },
    }
