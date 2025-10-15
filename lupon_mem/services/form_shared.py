import io
from datetime import datetime, date
import fitz
from django.db import connection
from django.core.exceptions import ValidationError
from django.contrib.staticfiles import finders

# ------------- General helpers -------------

def sanitize_text(s: str) -> str:
    if s is None:
        return ""
    s = str(s).strip()
    QUOTES = ('"', "“", "”", "‘", "’", "'")
    if len(s) >= 2 and s[0] in QUOTES and s[-1] in QUOTES:
        s = s[1:-1].strip()
    return s

def normalize(val):
    if val is None:
        return ""
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, dict):
        return ", ".join(str(x) for x in val.values())
    if isinstance(val, list):
        return ", ".join(str(x) for x in val)
    return str(val)

def to_int(x, default=None):
    try:
        return int(x)
    except Exception:
        return default

def to_float(x, default=None):
    try:
        return float(x)
    except Exception:
        return default

def find_static(path_or_static_key: str) -> str:
    return finders.find(path_or_static_key) or path_or_static_key

# ------------- DB loads -------------

def load_form_and_template(form_id: int):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT form_code, form_name, template_path FROM kp_form WHERE form_id=%s",
            [form_id],
        )
        row = cur.fetchone()
        if not row:
            raise ValidationError("Form not found.")
        form_code, form_name, template_path = row
    return form_code, form_name, find_static(template_path)

def load_fields_and_placements(form_id: int):
    with connection.cursor() as cur:
        cur.execute(
            """
          SELECT
            f.field_id,
            COALESCE(kff.label_override, f.base_label) as label,
            t.field_type_name,
            COALESCE(p.page_number, 1)              AS page_number,
            COALESCE(p.x, 36)                       AS x,
            COALESCE(p.y, 36)                       AS y,
            COALESCE(p.width, 0)                    AS width,
            COALESCE(p.height, 0)                   AS height,
            COALESCE(p.font_size, 11)               AS font_size,
            COALESCE(NULLIF(p.align, ''), 'left')   AS align
          FROM kp_form_field kff
          JOIN kp_field f ON f.field_id = kff.field_id
          JOIN kp_field_type t ON t.field_type_id = f.field_type_id
          LEFT JOIN kp_field_placement p
                 ON p.form_id = kff.form_id AND p.field_id = f.field_id
          WHERE kff.form_id=%s
          ORDER BY kff.sort_order, kff.kp_form_field_id
        """,
            [form_id],
        )
        return cur.fetchall()

def load_answers(submission_id: int):
    import json as _json
    answers = {}
    with connection.cursor() as cur:
        cur.execute(
            "SELECT field_id, value_json FROM blotter_kp_answer WHERE submission_id=%s",
            [submission_id],
        )
        for fid, v in cur.fetchall():
            try:
                parsed = _json.loads(v)
            except Exception:
                parsed = v
            if isinstance(parsed, str):
                parsed = sanitize_text(parsed)
            answers[str(fid)] = parsed
    return answers

def fetch_form_field_labels(form_id: int) -> list[tuple[int, str]]:
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT f.field_id, COALESCE(kff.label_override, f.base_label) AS label
            FROM kp_form_field kff
            JOIN kp_field f ON f.field_id = kff.field_id
            WHERE kff.form_id=%s
            ORDER BY kff.sort_order, kff.kp_form_field_id
        """,
            [form_id],
        )
        return [(fid, (lbl or "").strip()) for fid, lbl in cur.fetchall()]

# ------------- “answers-only” name mapping (generic) -------------

_LABEL_TO_KEY = {
    "complainant(s)": "complainants",
    "respondent(s)": "respondents",
    "barangay case no.": "brgy_case_number",
    "for": "purpose",
    "complaint": "complaint_details",
    "date filed": "date_filed",
    "time filed": "time_filed",
    "incident date": "incident_date",
    "incident time": "incident_time",
    "incident location": "incident_location",
    "date signed": "date_created",
    "subpoena to": "subpoena_to",
    "witness(es)": "subpoena_witness",
    "complainant signature name": "complainants",
}

_CASE_NO_VARIANTS = ("brgy_case_number", "brgy_case_num", "case_num")

_DUPLICATE_KEYS = {
    "complainants": ["complainants_2", "complainants_one", "complainants_two"],
    "respondents": ["respondents_2", "respondents_two", "respondents_three", "repondents", "repondents_one"],
    "brgy_case_number": ["brgy_case_num", "case_num"],
    "brgy_case_num": ["brgy_case_number", "case_num"],
    "case_num": ["brgy_case_number", "brgy_case_num"],
    "date_created": ["date_entered", "date_made", "date_signed"],
    "month_created": ["month_entered", "month_made", "month_signed"],
    "year_created": ["year_entered", "year_made", "year_signed", "year_received", "year_received_2"],
    "date_filed": ["date_month_scheduled"],
}

def _expand_duplicates(values: dict) -> dict:
    out = dict(values)
    from .form_shared import normalize  # self-import safe at runtime
    for k, dupes in _DUPLICATE_KEYS.items():
        base = out.get(k)
        if normalize(base):
            for dk in dupes:
                out.setdefault(dk, base)
    cval = next((out.get(k) for k in _CASE_NO_VARIANTS if out.get(k)), "")
    if normalize(cval):
        for k in _CASE_NO_VARIANTS:
            out.setdefault(k, cval)
    return out

def answers_to_names_strict(form_id: int, submission_id: int) -> dict:
    answers_by_id = load_answers(submission_id)
    labels = fetch_form_field_labels(form_id)
    values = {}

    for fid, label in labels:
        raw = answers_by_id.get(str(fid))
        if raw in (None, "", "null"):
            continue
        val = normalize(raw)

        lk = _LABEL_TO_KEY.get((label or "").strip().lower())
        if lk:
            values[lk] = val
            continue

        lbl = (label or "").strip()
        if lbl:
            values[lbl] = val

    return _expand_duplicates(values)

# ------------- PDF helpers -------------

def set_need_appearances(doc: fitz.Document):
    try:
        doc.set_need_appearances(True)
    except Exception:
        pass

def fill_acro_by_names(doc: fitz.Document, name_to_value: dict):
    set_need_appearances(doc)
    for page in doc:
        widgets = page.widgets() or []
        for w in widgets:
            fname = (w.field_name or "").strip()
            if not fname:
                continue
            if fname in name_to_value:
                val = normalize(name_to_value.get(fname, ""))
                try:
                    w.field_value = val
                    w.update()
                except Exception:
                    pass

def first_page_png(src: fitz.Document, scale: float = 1.5) -> bytes:
    page = src.load_page(0)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
    buf = io.BytesIO(pix.tobytes("png"))
    return buf.getvalue()
