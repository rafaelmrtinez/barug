from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse, HttpResponseNotAllowed
from django.views.decorators.http import require_http_methods
from django.db import transaction, connection
from django.conf import settings

from authentication.guards import session_login_required, role_required, LUPON_ROLES
from common.supabase_client import supabase

from lupon_mem.services.form_renderer import render_preview_png, render_final_pdf

from django.db import connection

LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}


def _has_role(request, allowed=LUPON_ROLES):
    # AttachProfileMiddleware should put staff role on request.user.profile
    roles = set(getattr(request, "user_roles", []))
    return bool(roles & allowed)


def case_list(request):
    if not _has_role(request):
        raise PermissionDenied()
    with connection.cursor() as cur:
        cur.execute("""
          SELECT bc.blotter_case_id, bc.blotter_case_num, bc.blotter_case_name,
                 bc.date_filed, ct.complaint_title_name, cn.case_name
            FROM blotter_case bc
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature cn ON cn.case_nature_id = bc.case_nature_id
           ORDER BY bc.blotter_case_id DESC
        """)
        rows = cur.fetchall()
    return render(request, "lupon_mem/case_list.html", {"rows": rows})


def case_detail(request, case_id:int):
    if not _has_role(request):
        raise PermissionDenied()
    with connection.cursor() as cur:
        cur.execute("""
          SELECT bc.blotter_case_id, bc.blotter_case_num, bc.blotter_case_name,
                 bc.date_filed, bc.incident_desc
            FROM blotter_case bc
           WHERE bc.blotter_case_id=%s
        """, [case_id])
        case = cur.fetchone()
        cur.execute("""
          SELECT s.submission_id, kf.form_code, kf.form_name, s.status, s.submitted_at
            FROM blotter_kp_submission s
            JOIN kp_form kf ON kf.form_id = s.form_id
           WHERE s.blotter_case_id=%s
           ORDER BY s.submitted_at DESC
        """, [case_id])
        forms = cur.fetchall()
    return render(request, "lupon_mem/case_detail.html", {"case": case, "forms": forms, "case_id": case_id})


def add_form_choose(request, case_id:int):
    if not _has_role(request):
        raise PermissionDenied()
    with connection.cursor() as cur:
        cur.execute("SELECT form_id, form_code, form_name FROM kp_form WHERE is_active IS TRUE ORDER BY form_code")
        forms = cur.fetchall()
    return render(request, "lupon_mem/add_form_choose.html", {"case_id": case_id, "forms": forms})


def form_builder(request, case_id:int, form_id:int=None, submission_id:int=None):
    if not _has_role(request):
        raise PermissionDenied()
    with connection.cursor() as cur:
        if submission_id:
            cur.execute("""
              SELECT s.submission_id, s.form_id, kf.form_code, kf.form_name
                FROM blotter_kp_submission s
                JOIN kp_form kf ON kf.form_id = s.form_id
               WHERE s.submission_id=%s
            """, [submission_id])
        else:
            cur.execute("""
              SELECT kf.form_id, kf.form_code, kf.form_name
                FROM kp_form kf WHERE kf.form_id=%s
            """, [form_id])
        hdr = cur.fetchone()

        fid = hdr[1] if submission_id else hdr[0]
        cur.execute("""
          SELECT kff.kp_form_field_id, f.field_id, COALESCE(kff.label_override, f.base_label) AS label,
                 t.field_type_name, kff.is_required
            FROM kp_form_field kff
            JOIN kp_field f ON f.field_id = kff.field_id
            JOIN kp_field_type t ON t.field_type_id = f.field_type_id
           WHERE kff.form_id=%s
           ORDER BY kff.sort_order, kff.kp_form_field_id
        """, [fid])
        fields = cur.fetchall()

        # load existing answers if editing
        answers = {}
        if submission_id:
            cur.execute("""
              SELECT a.field_id, a.value_json
                FROM blotter_kp_answer a
               WHERE a.submission_id=%s
            """, [submission_id])
            for f_id, val in cur.fetchall():
                answers[str(f_id)] = val

    return render(request, "lupon_mem/form_builder.html", {
        "case_id": case_id,
        "submission_id": submission_id,
        "form_id": fid,
        "header": hdr,
        "fields": fields,
        "answers": answers
    })

@require_http_methods(["POST"])
def save_answers(request):
    if not _has_role(request):
        return HttpResponseForbidden()
    data = request.POST
    case_id = int(data["case_id"])
    form_id = int(data["form_id"])
    submission_id = data.get("submission_id")

    import json
    payload = json.loads(data["answers"])  # {field_id: value}

    with transaction.atomic():
        with connection.cursor() as cur:
            if submission_id:
                sid = int(submission_id)
            else:
                # create new submission in DRAFT
                cur.execute("""
                  INSERT INTO blotter_kp_submission(blotter_case_id, form_id, status)
                  VALUES (%s,%s,'DRAFT') RETURNING submission_id
                """, [case_id, form_id])
                sid = cur.fetchone()[0]

            # upsert answers
            for field_id, value in payload.items():
                cur.execute("""
                  INSERT INTO blotter_kp_answer(submission_id, field_id, value_json)
                  VALUES (%s,%s,%s)
                  ON CONFLICT (submission_id, field_id)
                  DO UPDATE SET value_json=EXCLUDED.value_json
                """, [sid, int(field_id), json.dumps(value)])

    return JsonResponse({"ok": True, "submission_id": sid})

@require_http_methods(["POST"])
def submit_form(request):
    if not _has_role(request):
        return HttpResponseForbidden()
    import json
    data = json.loads(request.body.decode())
    submission_id = int(data["submission_id"])
    case_id = int(data["case_id"])

    # render final PDF and store
    pdf_bytes, filename = render_final_pdf(submission_id=submission_id)

    # upload to Supabase bucket (optional; or write to disk)
    bucket = settings.SUPABASE_BUCKET or "documents"
    supabase.storage.from_(bucket).upload(f"blotter/{case_id}/{filename}", pdf_bytes, {
        "contentType": "application/pdf",
        "upsert": True
    })

    # mark submitted
    with connection.cursor() as cur:
        cur.execute("UPDATE blotter_kp_submission SET status='SUBMITTED', submitted_at=now() WHERE submission_id=%s", [submission_id])

    return JsonResponse({"ok": True, "file": filename})

def preview_image(request):
    if not _has_role(request):
        return HttpResponseForbidden()
    # params: form_id, case_id, submission_id (optional), draft answers (optional)
    form_id = int(request.GET["form_id"])
    submission_id = request.GET.get("submission_id")
    answers_json = request.GET.get("answers")

    img_bytes = render_preview_png(form_id=form_id, submission_id=submission_id, answers_json=answers_json)
    return HttpResponse(img_bytes, content_type="image/png")
