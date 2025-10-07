import io, json, fitz
from django.db import connection
from django.conf import settings
from datetime import datetime

def _load_form_and_template(form_id:int):
    with connection.cursor() as cur:
        cur.execute("SELECT form_code, form_name, template_path FROM kp_form WHERE form_id=%s", [form_id])
        form_code, form_name, template_path = cur.fetchone()
    # template_path should be in STATIC dirs; resolve an absolute path:
    import os
    from django.contrib.staticfiles import finders
    abs_path = finders.find(template_path) or template_path  # fallback if absolute
    return form_code, form_name, abs_path

def _load_fields_and_placements(form_id:int):
    with connection.cursor() as cur:
        cur.execute("""
          SELECT f.field_id, COALESCE(kff.label_override, f.base_label) as label, t.field_type_name,
                 p.page_number, p.x, p.y, p.width, p.height, COALESCE(p.font_size, 11), p.align
            FROM kp_form_field kff
            JOIN kp_field f ON f.field_id = kff.field_id
            JOIN kp_field_type t ON t.field_type_id = f.field_type_id
            LEFT JOIN kp_field_placement p ON p.form_id=kff.form_id AND p.field_id=f.field_id
           WHERE kff.form_id=%s
        """, [form_id])
        return cur.fetchall()

def _load_answers(submission_id:int):
    answers={}
    with connection.cursor() as cur:
        cur.execute("SELECT field_id, value_json FROM blotter_kp_answer WHERE submission_id=%s", [submission_id])
        for fid, v in cur.fetchall():
            answers[str(fid)] = v
    return answers

def _normalize(val):
    if val is None: return ""
    if isinstance(val, (int,float)): return str(val)
    if isinstance(val, (dict,list)): return ", ".join(map(_normalize, val if isinstance(val,list) else val.values()))
    return str(val)

def render_preview_png(form_id:int, submission_id=None, answers_json=None):
    form_code, form_name, tpl_path = _load_form_and_template(form_id)
    doc = fitz.open(tpl_path)
    page = doc.load_page(0)   # render first page for speed; multi-page is similar

    # answers priority: in-flight answers_json > DB
    cur_answers = {}
    if submission_id:
        cur_answers.update(_load_answers(int(submission_id)))
    if answers_json:
        cur_answers.update(json.loads(answers_json))

    # draw text on a **copy** for preview
    for (field_id, label, ftype, pg, x, y, w, h, font_size, align) in _load_fields_and_placements(form_id):
        if pg != 1: continue  # simple preview: page1 only; final renderer handles all pages
        val = _normalize(cur_answers.get(str(field_id), "")) or ""
        if not val: continue
        point = fitz.Point(float(x), float(y))
        page.insert_text(point, val, fontsize=float(font_size), fontname="helv")

    # rasterize to PNG
    pix = page.get_pixmap(matrix=fitz.Matrix(1.5,1.5))
    buf = io.BytesIO(pix.tobytes("png"))
    return buf.getvalue()

def render_final_pdf(submission_id:int):
    # draw on ALL pages for final
    with connection.cursor() as cur:
        cur.execute("SELECT form_id, blotter_case_id FROM blotter_kp_submission WHERE submission_id=%s", [submission_id])
        form_id, case_id = cur.fetchone()

    form_code, form_name, tpl_path = _load_form_and_template(form_id)
    answers = _load_answers(submission_id)
    placements = _load_fields_and_placements(form_id)

    src = fitz.open(tpl_path)
    # note: PyMuPDF uses bottom-left origin; your placements assumed top-left.
    # If your coords are measured top-left, convert y = page_height - y
    for (field_id, _label, _ft, pg, x, y, w, h, fs, align) in placements:
        p = src.load_page(pg-1)
        page_h = p.rect.height
        val = _normalize(answers.get(str(field_id), "")) or ""
        if not val: continue
        tx = float(x)
        ty = page_h - float(y)  # flip Y
        p.insert_text(fitz.Point(tx, ty), val, fontsize=float(fs), fontname="helv")

    out = io.BytesIO()
    src.save(out)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{form_code}_CASE{case_id}_{ts}.pdf"
    return out.getvalue(), filename
