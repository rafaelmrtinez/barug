# treasurer/services/dashboard_api.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any, Dict, List, Tuple
from zoneinfo import ZoneInfo

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from authentication.supabase_client import supabase


# ────────────────────────── constants ──────────────────────────
PH_TZ = ZoneInfo("Asia/Manila")
UTC = dt_timezone.utc  # Django 5: don't use timezone.utc


# Where to read requests from (wide “list” view or mat. view)
SOURCE_TABLE = "v_doc_request_list_ex_v2"


# ─────────────────────── small time helpers ───────────────────────

@dataclass
class Range:
    start_utc: datetime                 # inclusive
    end_utc: datetime                   # inclusive
    label_points: List[str]             # display labels for the trend
    bucket_starts_utc: List[datetime]   # per-day bucket starts (UTC)


def _ph_day_bounds_utc(d: datetime) -> Tuple[datetime, datetime]:
    """
    Given any PH-local aware dt `d`, return (00:00, 23:59:59.999) for that PH day, as UTC.
    """
    d_local = timezone.localtime(d, PH_TZ)
    start_local = d_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1) - timedelta(milliseconds=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def _last_n_days_range(n: int) -> Range:
    """
    Last `n` days including today, PH-local, returned as UTC bounds and day buckets.
    """
    today_local = timezone.localtime(timezone.now(), PH_TZ).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    # Build buckets oldest→newest
    buckets_local = [today_local - timedelta(days=i) for i in reversed(range(n))]
    bucket_starts_utc = [
        b.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        for b in buckets_local
    ]
    start_utc, _ = _ph_day_bounds_utc(buckets_local[0])
    _, end_utc = _ph_day_bounds_utc(buckets_local[-1])

    labels = [b.strftime("%a") for b in buckets_local]  # Mon, Tue, ...

    return Range(
        start_utc=start_utc,
        end_utc=end_utc,
        label_points=labels,
        bucket_starts_utc=bucket_starts_utc,
    )


def _range_for_key(range_key: str) -> Range:
    rk = (range_key or "").lower()
    if rk in ("7d", "last7", "week"):
        return _last_n_days_range(7)
    if rk in ("30d", "last30"):
        # chart still buckets by day; labels will be day numbers
        r = _last_n_days_range(30)
        # prettier labels for 30d: "Oct 02", "Oct 03", ...
        today_local = timezone.localtime(timezone.now(), PH_TZ)
        days = [today_local - timedelta(days=i) for i in reversed(range(30))]
        r.label_points = [d.strftime("%b %d") for d in days]
        return r
    # default: 7d
    return _last_n_days_range(7)


# ───────────────────── data fetchers (QB only) ─────────────────────

def kpi_doc_requests_today(doc_type: str | None) -> int:
    """
    Count of doc requests created today (PH) — pure query builder.
    """
    today_local = timezone.localtime(timezone.now(), PH_TZ)
    start_utc, end_utc = _ph_day_bounds_utc(today_local)

    qb = (
        supabase.table(SOURCE_TABLE)
        .select("doc_request_id", count="exact")
        .gte("created_at", start_utc.isoformat())
        .lte("created_at", end_utc.isoformat())
    )
    if doc_type:
        # doc_types is an array in the view
        qb = qb.contains("doc_types", [doc_type])

    res = qb.execute()
    return int(getattr(res, "count", 0) or 0)


def _fetch_requests_in_range(range_key: str, doc_type: str | None) -> List[dict]:
    """
    Pull rows for the chosen range; small cap to keep it fast in UI.
    """
    r = _range_for_key(range_key)
    qb = (
        supabase.table(SOURCE_TABLE)
        .select("doc_request_id, created_at, status, doc_types", count="exact")
        .gte("created_at", r.start_utc.isoformat())
        .lte("created_at", r.end_utc.isoformat())
        .order("created_at", desc=False)
        .limit(5000)
    )
    if doc_type:
        qb = qb.contains("doc_types", [doc_type])

    res = qb.execute()
    return list(getattr(res, "data", []) or [])


def _bucket_by_day(rows: List[dict], range_obj: Range) -> List[int]:
    """
    Client-side group-by-day using PH timezone. Robust to various ISO formats.
    """
    # Prepare next-day edges for buckets
    edges = [b + timedelta(days=1) for b in range_obj.bucket_starts_utc]
    counts = [0] * len(range_obj.bucket_starts_utc)

    def _to_utc(ts: str | datetime | None) -> datetime | None:
        if not ts:
            return None
        if isinstance(ts, datetime):
            dt = ts
        else:
            # Supabase returns ISO strings: "...Z" or with "+08:00" etc.
            dt = parse_datetime(str(ts))
        if dt is None:
            return None
        if timezone.is_naive(dt):
            # Assume UTC if no tzinfo
            dt = dt.replace(tzinfo=dt_timezone.utc)
        return dt.astimezone(UTC)

    for row in rows:
        dt = _to_utc(row.get("created_at"))
        if not dt:
            continue
        # place into a bucket (linear scan is fine for <= 30 buckets)
        for i, (start, end) in enumerate(zip(range_obj.bucket_starts_utc, edges)):
            if start <= dt < end:
                counts[i] += 1
                break
    return counts


def _status_breakdown(rows: List[dict]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in rows:
        s = (r.get("status") or "").upper()
        if not s:
            continue
        out[s] = out.get(s, 0) + 1
    return out


# ───────────────────────── public facade ─────────────────────────

def build_dashboard_payload(range_key: str = "7d", doc_type: str | None = None) -> Dict[str, Any]:
    """
    Returns a dict the template can json_script into window:
      {
        "kpis": {...},
        "requestsTrend": { "labels": [...], "data": [...] },
        "statusBreakdown": { "labels": [...], "data": [...] }
      }
    """
    # KPIs
    kpis = {
        "doc_requests_today": kpi_doc_requests_today(doc_type),
        # Future: add more KPIs when data sources are ready
        # "pending_verifications": ...,
        # "active_businesses": ...,
        # "residents_total": ...,
    }

    # Series
    range_obj = _range_for_key(range_key)
    rows = _fetch_requests_in_range(range_key, doc_type)

    trend_counts = _bucket_by_day(rows, range_obj)
    status_counts_map = _status_breakdown(rows)

    # nicer labels for statuses (map known ones)
    LABEL_MAP = {
        "FOR CLERK REVIEW": "Pending",
        "FOR_TREASURER_REVIEW": "Treasurer Review",
        "FOR PRINTING": "For Printing",
        "FOR_PRINTING": "For Printing",
        "READY_FOR_PICKUP": "Ready for Pickup",
        "RELEASED": "Released",
        "DECLINED": "Rejected",
        "REFUNDED": "Refunded",
        "PAID": "Paid",
        "PENDING": "Pending",
        "PROCESSING": "Processing",
        "APPROVED": "Approved",
        "REJECTED": "Rejected",
    }

    # order for the donut
    ORDER = [
        "FOR CLERK REVIEW", "FOR_TREASURER_REVIEW", "PAID", "FOR_PRINTING",
        "READY_FOR_PICKUP", "RELEASED", "DECLINED", "REFUNDED",
    ]

    labels: List[str] = []
    data: List[int] = []

    for key in ORDER:
        if key in status_counts_map:
            labels.append(LABEL_MAP.get(key, key.title()))
            data.append(status_counts_map[key])

    # include any unexpected statuses at the end
    for k, v in status_counts_map.items():
        if k not in ORDER:
            labels.append(LABEL_MAP.get(k, k.title()))
            data.append(v)

    return {
        "kpis": kpis,
        "requestsTrend": {
            "labels": range_obj.label_points,
            "data": trend_counts,
        },
        "statusBreakdown": {
            "labels": labels,
            "data": data,
        },
    }
