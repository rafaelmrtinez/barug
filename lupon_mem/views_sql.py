# lupon_mem/views_sql.py
from django.db import connection
from django.http import Http404, HttpResponseNotAllowed
from django.utils.timezone import localtime
from django.views.generic import TemplateView
from django.views import View
from django.shortcuts import redirect
import json


def fetch_submission(submission_id: int):
    """
    Returns (sub, items)
      - sub: dict with submission + form metadata
      - items: list[dict] with field meta + value_json and display_value
    """
    # --- submission + form ---
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT s.submission_id,
                   s.blotter_case_id,
                   s.form_id,
                   s.status,
                   s.submitted_at,
                   f.form_code,
                   f.form_name
              FROM blotter_kp_submission s
              JOIN kp_form f ON f.form_id = s.form_id
             WHERE s.submission_id = %s
            """,
            [submission_id],
        )
        row = cur.fetchone()

    if not row:
        raise Http404(f"Submission #{submission_id} not found.")

    sub = {
        "submission_id":   row[0],
        "blotter_case_id": row[1],
        "form_id":         row[2],
        "status":          row[3],
        "submitted_at":    row[4],
        "form_code":       row[5],
        "form_name":       row[6],
    }

    # --- fields + answers for this submission ---
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT
              kff.kp_form_field_id,
              kff.sort_order,
              kff.is_required,
              COALESCE(kff.label_override, kf.base_label) AS label,
              kf.field_id,
              kf.field_code,
              ft.field_type_name,
              a.value_json
            FROM kp_form_field kff
            JOIN kp_field kf      ON kf.field_id = kff.field_id
            JOIN kp_field_type ft ON ft.field_type_id = kf.field_type_id
            LEFT JOIN blotter_kp_answer a
              ON a.submission_id = %s AND a.field_id = kff.field_id
            WHERE kff.form_id = %s
            ORDER BY kff.sort_order, kff.kp_form_field_id
            """,
            [submission_id, sub["form_id"]],
        )
        rows = cur.fetchall()

    def fmt(v):
        """Turn any JSON-ish value into a friendly string for display."""
        if v is None:
            return "—"
        if isinstance(v, (list, tuple)):
            # join simple lists; fallback to JSON if nested
            try:
                return ", ".join("" if x is None else str(x) for x in v)
            except Exception:
                return json.dumps(v, ensure_ascii=False)
        if isinstance(v, dict):
            return json.dumps(v, ensure_ascii=False)
        # booleans for checkboxes look nicer as Yes/No
        if isinstance(v, bool):
            return "Yes" if v else "No"
        return str(v)

    items = []
    for r in rows:
        value_json = r[7]
        items.append({
            "kp_form_field_id": r[0],
            "sort_order":       r[1],
            "is_required":      r[2],
            "label":            r[3],
            "field_id":         r[4],
            "field_code":       r[5],
            "field_type":       r[6],
            "value_json":       value_json,
            "display_value":    fmt(value_json),
        })

    return sub, items


class SubmissionViewSQL(TemplateView):
    template_name = "lupon_mem/submissions/view.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        submission_id = int(self.kwargs["pk"])

        sub, items = fetch_submission(submission_id)

        submitted_at_local = localtime(sub["submitted_at"]) if sub["submitted_at"] else None
        ctx.update({
            "sub": {
                **sub,
                "submitted_at_local": submitted_at_local,
                "is_submitted": str(sub["status"] or "").upper() == "SUBMITTED",
            },
            "items": items,
        })
        return ctx


class SubmissionEditSQL(View):
    """Redirects /submissions/<pk>/edit/ to your existing editor route."""
    def get(self, request, pk, *args, **kwargs):
        sub, _ = fetch_submission(int(pk))
        return redirect("lupon_mem:form_edit",
                        case_id=sub["blotter_case_id"],
                        submission_id=sub["submission_id"])


class SubmissionUpdateSQL(View):
    """Placeholder to satisfy imports; your saving still uses your API endpoints."""
    def post(self, request, pk, *args, **kwargs):
        return HttpResponseNotAllowed(["GET", "HEAD"])

    def get(self, request, pk, *args, **kwargs):
        return redirect("lupon_mem:kp_submission_view", pk=pk)
