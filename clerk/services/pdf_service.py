from __future__ import annotations
from typing import Any, Dict, List
import io, os
from datetime import datetime
from django.utils import timezone
from django.conf import settings

try:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, BooleanObject
except Exception:
    PdfReader = PdfWriter = None  # type: ignore

from .subject_service import subject_view, pick  # reuse subject logic

def _pdf_templates_dir() -> str:
    base = getattr(settings, "PDF_TEMPLATES_DIR", None)
    return str(base) if base else str(getattr(settings, "BASE_DIR") / "pdf_templates")

def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)

def _date_parts(dt: datetime):
    return dt.strftime("%d"), dt.strftime("%B"), dt.strftime("%Y")

def _humanize_purpose(val: Any) -> str:
    s = _safe_str(val).strip()
    return s.replace("_", " ").title() if s else ""

def _choose_template(doc_name: str, _is_minor_ignored: bool) -> str:
    name = (doc_name or "").lower()
    if "indigency" in name or "indegency" in name:
        return "barangay-indegency.pdf"
    if "low" in name and "income" in name:
        return "barangay-cert-of-low-income.pdf"
    if "death" in name:
        return "barangay-death-cert.pdf"
    if "permit" in name:
        return "barangay-permit.pdf"
    return "barangay-clearance.pdf"

def _get_all_pdf_field_names(template_path: str) -> List[str]:
    names: List[str] = []
    if PdfReader is None: return names
    r = PdfReader(template_path)
    try:
        fdict = r.get_form_text_fields()
        if fdict: names.extend(list(fdict.keys()))
    except Exception:
        try:
            fdict = r.get_fields()
            if fdict: names.extend(list(fdict.keys()))
        except Exception:
            pass
    for page in r.pages:
        annots = page.get("/Annots")
        if not annots: continue
        for a in annots:
            obj = a.get_object()
            if obj.get("/Subtype") == "/Widget":
                nm = obj.get("/T")
                if nm:
                    nm = str(nm).strip("()")
                    if nm not in names: names.append(nm)
    return names

def _fill_pdf_with_values(template_path: str, merged: Dict[str, str]) -> bytes:
    if PdfReader is None: raise RuntimeError("pypdf is not installed. Run: pip install pypdf")
    reader = PdfReader(template_path)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    if "/AcroForm" in writer._root_object:
        writer._root_object["/AcroForm"].update({NameObject("/NeedAppearances"): BooleanObject(True)})
    for page in writer.pages:
        writer.update_page_form_field_values(page, merged)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()

def _fill_fields_for_line(header: Dict[str, Any], line: Dict[str, Any]) -> Dict[str, str]:
    now = timezone.localtime()
    d, m, y = _date_parts(now)

    subj = subject_view(header, line)
    subject_full_name  = _safe_str(subj["full_name"])
    subject_addr       = _safe_str(subj["address"])
    subject_age        = _safe_str(subj["age"])
    subject_civil      = _safe_str(subj["civil_status"])
    subject_nat        = _safe_str(subj["nationality"])

    barangay = "Señor Santo Niño"
    city     = _safe_str(header.get("city") or "Cebu City")
    province = _safe_str(header.get("province") or "Cebu")

    purpose = _humanize_purpose(
        line.get("purpose_display")
        or line.get("purpose_label")
        or line.get("purpose")
        or line.get("purpose_code")
        or (line.get("details") or {}).get("purpose_code")
    )

    line_total = _safe_str(pick(line.get("line_total"), "", allow_zero=True))
    or_no = _safe_str(
        pick(
            line.get("or_number"),
            header.get("or_number"),
            (header.get("payments") or {}).get("latest_or_number"),
        )
    )
    captain  = _safe_str(header.get("captain_name") or "Lourdes R. Ramirez")
    doc_name = _safe_str(line.get("document_type_name")).lower()

    if "clearance" in doc_name:
        return {
            "requestor_full_name": subject_full_name,
            "requestor_age": subject_age,
            "requestor_civil_status": subject_civil,
            "requestor_addr": subject_addr,
            "doc_purpose": purpose,
            "date_issued": d, "month_issued": m, "year_issued": y,
            "barangay_issued": barangay, "city_mun_issued": city, "province_issued": province,
            "brgy_captain": captain, "totla_amnt": line_total, "or_number": or_no,
        }

    if "indigency" in doc_name or "indegency" in doc_name:
        return {
            "requestor_full_name": subject_full_name,
            "requestor_age": subject_age,
            "requestor_civil_status": subject_civil,
            "requestor_nationality": subject_nat,
            "requestor_barangay": barangay, "requestor_city_mun": city, "requestor_province": province,
            "requesition_purpose": purpose,
            "issued_date": d, "issued_month": m, "issued_year": y,
            "barangay_issued": barangay, "city_mun_issued": city, "province_issued": province,
            "brgy_captain": captain, "total_amnt": line_total, "or_number": or_no,
        }

    if "low" in doc_name and "income" in doc_name:
        return {
            "full_name": subject_full_name, "age": subject_age, "civil_status": subject_civil, "nationality": subject_nat,
            "barangay_name": barangay, "city_municipality": city, "province": province,
            "total_earning": _safe_str(line.get("monthly_income") or ""), "purpose": purpose,
            "day": d, "month": m, "year": y,
            "issued_at_brgy": barangay, "issued_at_city_municipality": city, "issued_at_province": province,
            "amnt": line_total, "official_reciept": or_no,
        }

    if "death" in doc_name:
        return {
            "requestor_full_name": subject_full_name,
            "deceased_civil_status": subject_civil, "deceased_nationality": subject_nat,
            "deceased_barangay": barangay, "deceased_city_mun": city, "deceased_province": province,
            "date_of_death": _safe_str(line.get("death_day") or d),
            "month_of_death": _safe_str(line.get("death_month") or m),
            "year_of_death": _safe_str(line.get("death_year") or y),
            "place_of_death": _safe_str(line.get("place_of_death") or ""),
            "curr_date": d, "curr_month": m, "curr_year": y,
            "barangay_issued": barangay, "city_mun_issued": city, "province_issued": province,
            "brgy_captain": captain, "total_amnt": line_total, "or_number": or_no,
        }

    if "permit" in doc_name:
        event_dt = _safe_str(line.get("event_date_time") or "")
        return {
            "requestor_org": _safe_str(line.get("org_name") or ""), "requestor_name": subject_full_name,
            "requested_event": _safe_str(line.get("event_name") or ""), "event_location": _safe_str(line.get("event_location") or ""),
            "barangay_name": barangay, "brgy_date_time": event_dt,
            "issued_date": d, "issued_month": m, "issued_year": y,
            "barangay_issued": barangay, "cty_mun_issued": city, "province_issued": province,
            "brgy_capt": captain, "total_amnt": line_total, "or_number": or_no,
        }

    return {}
