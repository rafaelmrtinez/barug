import io
from datetime import datetime
import fitz
from django.core.exceptions import ValidationError
from django.db import connection  # re-expose for handlers that import it through FS
from . import form_shared as FS
from .forms import get_handler

# ----------------------------
# Preview
# ----------------------------

def render_preview_png(form_id: int, submission_id=None, answers_json=None):
    form_code, form_name, tpl_path = FS.load_form_and_template(form_id)
    if not tpl_path:
        raise ValidationError("Template path not configured.")
    src = fitz.open(tpl_path)
    return FS.first_page_png(src, 1.5)

# ----------------------------
# Final PDF (answers-only)
# ----------------------------

def render_final_pdf(submission_id: int):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT form_id, blotter_case_id FROM blotter_kp_submission WHERE submission_id=%s",
            [submission_id],
        )
        row = cur.fetchone()
        if not row:
            raise ValidationError("Submission not found.")
        form_id, case_id = row

    form_code, form_name, tpl_path = FS.load_form_and_template(form_id)
    if not tpl_path:
        raise ValidationError("Template path not configured.")

    try:
        src = fitz.open(tpl_path)
    except Exception:
        raise ValidationError("Cannot open template PDF.")

    # Decide how to build name→value mapping
    handler = get_handler(form_code)
    has_widgets = any((page.widgets() or []) for page in src)

    if has_widgets:
        # AcroForm path: use either specialized handler or generic handler
        name_to_value = handler.build_name_value_map(form_id, submission_id)
        
        # Persist computed values if handler supports it
        if hasattr(handler, 'persist_computed'):
            handler.persist_computed(
                form_id=form_id,
                submission_id=submission_id,
                case_id=case_id,
                out_map=name_to_value
            )
        
        FS.fill_acro_by_names(src, name_to_value)
    else:
        # Non-Acro path (draw text to coordinates) — answers-only, generic behavior
        answers = FS.load_answers(submission_id)          # {field_id: value}
        placements = FS.load_fields_and_placements(form_id)

        # group placements for scaling per page
        page_groups = {}
        for (field_id, _label, _ft, pg, x, y, w, h, fs, align) in placements:
            pg_i = FS.to_int(pg, 1)
            if pg_i < 1:
                pg_i = 1
            g = page_groups.setdefault(pg_i, {"items": [], "max_x": 0.0, "max_y": 0.0})
            fx = FS.to_float(x, None)
            fy = FS.to_float(y, None)
            fw = FS.to_float(w, 0.0) if w is not None else 0.0
            fh = FS.to_float(h, 0.0) if h is not None else 0.0
            g["items"].append((field_id, _label, _ft, pg_i, fx, fy, fw, fh, fs, align))
            if fx is not None:
                g["max_x"] = max(g["max_x"], fx + fw)
            if fy is not None:
                g["max_y"] = max(g["max_y"], fy + fh)

        for pg_i, g in page_groups.items():
            if pg_i > src.page_count:
                pg_i = src.page_count
            page = src.load_page(pg_i - 1)
            page_w = page.rect.width
            page_h = page.rect.height

            design_w = g["max_x"] or page_w
            design_h = g["max_y"] or page_h
            sx = page_w / design_w if design_w > 0 else 1.0
            sy = page_h / design_h if design_h > 0 else 1.0

            for (field_id, _label, _ft, _pg, fx, fy, fw, fh, fs, align) in g["items"]:
                if fx is None or fy is None:
                    continue
                text = FS.normalize(answers.get(str(field_id)))
                if not text:
                    continue
                fz = FS.to_float(fs, 10.0)

                left = fx * sx
                top = page_h - (fy * sy)
                width = max(0.0, (FS.to_float(fw, 0.0) * sx))
                height = max(0.0, (FS.to_float(fh, 0.0) * sy))
                a = (align or "left").lower()
                if a not in ("left", "center", "right"):
                    a = "left"

                if width > 0 and height > 0:
                    bottom = top - height
                    right = left + width
                    rect = fitz.Rect(left, bottom, right, top)
                    page.insert_textbox(
                        rect,
                        text,
                        fontsize=fz,
                        fontname="helv",
                        align={"left": 0, "center": 1, "right": 2}[a],
                    )
                else:
                    x = left
                    if a != "left":
                        try:
                            tw = page.get_text_length(text, fontsize=fz, fontname="helv")
                            if a == "center":
                                x = left - tw / 2.0
                            elif a == "right":
                                x = left - tw
                        except Exception:
                            pass
                    page.insert_text(fitz.Point(x, top), text, fontsize=fz, fontname="helv")

    # Save / return
    out = io.BytesIO()
    src.save(out, deflate=True, garbage=3)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{form_code}_CASE{case_id}_{ts}.pdf"
    return out.getvalue(), filename
