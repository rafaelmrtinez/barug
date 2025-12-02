# ============================================================
# pdf_service.py — PDF helpers + Business Clearance field map
# ============================================================

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
from authentication.supabase_client import supabase

# ────────────────────────────────────────────────────────────
# SECTION: Business Clearance → PDF field name map
# (Fill/adjust these after inspecting the PDF field names)
# ────────────────────────────────────────────────────────────
BUSINESS_CLEARANCE_FIELD_MAP: Dict[str, str] = {
    # Applicant block
    "applicant_nationality":   "Text Box 1",     # CORRECT
    "applicant_full_name":     "Text Box 1_2",   # CORRECT
    "applicant_age":           "Text Box 1_3",   # CORRECT

    # Application no / date applied (your notes said WALA; we’ll still map them)
    "numberfour":              "Text Box 1_4",   # Application No.
    "numberfour=":             "Text Box 1_4",   # (typo-safe alias → same box)
    "numberfive":              "Text Box 1_5",   # Date Applied

    # Business block
    "business_name_style":     "Text Box 1_6",   # CORRECT
    "business_address":        "Text Box 1_7",   # CORRECT
    "capital_invested":        "Text Box 1_8",   # CORRECT

    # Lines of business (1..5)
    "lines_of_business_1":     "Text Box 1_9",   # CORRECT
    "lines_of_business_2":     "Text Box 1_10",  # CORRECT
    "lines_of_business_3":     "Text Box 1_11",  # CORRECT
    "lines_of_business_4":     "Text Box 1_12",  # CORRECT
    "lines_of_business_5":     "Text Box 1_13",  # CORRECT

    "gross_sales_prev_year":   "Text Box 1_14",  # CORRECT

    # Footer / receipt block
    "requestor_full_name":     "Text Box 1_15",  # CORRECT
    "numbersixteen":           "Text Box 1_16",  # Punong Brgy.
    "or_number":               "Text Box 1_17",  # CORRECT
    "paid_date":               "Text Box 1_18",  # CORRECT
    "paid_amount":             "Text Box 1_19",  # CORRECT
}

# ────────────────────────────────────────────────────────────
# SECTION: Basic helpers
# ────────────────────────────────────────────────────────────
def _pdf_templates_dir() -> str:
    base = getattr(settings, "PDF_TEMPLATES_DIR", None)
    return str(base) if base else str(getattr(settings, "BASE_DIR") / "pdf_templates")

def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)

def _get_barangay_captain_name() -> str:
    """Fetch the current barangay captain name from database"""
    try:
        # Get active staff with role_id=3 (Barangay Captain)
        result = supabase.table("staff").select("person_id").eq("role_id", 3).eq("acc_status_id", 1).limit(1).execute()
        if result.data and len(result.data) > 0:
            person_id = result.data[0].get("person_id")
            if person_id:
                # Get person details
                person_result = supabase.table("person").select("first_name, middle_name, last_name, suffix").eq("person_id", person_id).single().execute()
                if person_result.data:
                    first = _safe_str(person_result.data.get("first_name", ""))
                    middle = _safe_str(person_result.data.get("middle_name", ""))
                    last = _safe_str(person_result.data.get("last_name", ""))
                    suffix = _safe_str(person_result.data.get("suffix", ""))
                    
                    # Format: First M. Last Suffix
                    middle_initial = f"{middle[0]}." if middle else ""
                    name_parts = [first, middle_initial, last]
                    if suffix:
                        name_parts.append(suffix)
                    captain_name = " ".join(p for p in name_parts if p)
                    print(f"[CAPTAIN DEBUG] Fetched captain name: {captain_name}")
                    return captain_name
    except Exception as e:
        print(f"[CAPTAIN DEBUG] Failed to fetch captain name: {e}")
    
    # Fallback to default
    return "Lourdes R. Ramirez"

def _date_parts(dt: datetime):
    day = dt.strftime("%d")
    month = dt.strftime("%B")
    year = dt.strftime("%Y")
    print(f"[DATE_PARTS DEBUG] Generated date parts: day={day}, month={month}, year={year}")
    return day, month, year

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
    if "residency" in name:
        return "barangay-residency.pdf"
    return "barangay-clearance.pdf"

def _get_all_pdf_field_names(template_path: str) -> List[str]:
    names: List[str] = []
    if PdfReader is None:
        return names
    r = PdfReader(template_path)
    try:
        fdict = r.get_form_text_fields()
        if fdict:
            names.extend(list(fdict.keys()))
    except Exception:
        try:
            fdict = r.get_fields()
            if fdict:
                names.extend(list(fdict.keys()))
        except Exception:
            pass
    for page in r.pages:
        annots = page.get("/Annots")
        if not annots:
            continue
        for a in annots:
            obj = a.get_object()
            if obj.get("/Subtype") == "/Widget":
                nm = obj.get("/T")
                if nm:
                    nm = str(nm).strip("()")
                    if nm not in names:
                        names.append(nm)
    return names

def _fill_pdf_with_values(template_path: str, merged: Dict[str, str], is_ctc: bool = False) -> bytes:
def _fill_pdf_with_values(template_path: str, merged: Dict[str, str], is_ctc: bool = False) -> bytes:
    if PdfReader is None:
        raise RuntimeError("pypdf is not installed. Run: pip install pypdf")
    
    # Convert all values to uppercase
    merged = {k: str(v).upper() if v else v for k, v in merged.items()}
    
    print(f"[PDF DEBUG] Reading template: {template_path}")
    print(f"[PDF DEBUG] Template exists: {os.path.exists(template_path)}")
    print(f"[PDF DEBUG] Values to fill: {len(merged)} fields")
    print(f"[PDF DEBUG] Is CTC: {is_ctc}")
    print(f"[PDF DEBUG] Is CTC: {is_ctc}")
    
    reader = PdfReader(template_path)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    
    # Check if PDF has form fields
    form_fields = reader.get_form_text_fields() if hasattr(reader, 'get_form_text_fields') else {}
    print(f"[PDF DEBUG] Form fields found: {len(form_fields)}")
    print(f"[PDF DEBUG] ALL Form field names: {list(form_fields.keys())}")
    print(f"[PDF DEBUG] ALL Form field names: {list(form_fields.keys())}")
    
    if "/AcroForm" in writer._root_object:
        writer._root_object["/AcroForm"].update({NameObject("/NeedAppearances"): BooleanObject(True)})
        print(f"[PDF DEBUG] AcroForm found and NeedAppearances set")
    else:
        print(f"[PDF DEBUG] No AcroForm found in PDF")
    
    # Set center alignment for year field
    from pypdf.generic import NumberObject
    for page in writer.pages:
        annots = page.get('/Annots')
        if annots:
            for annot_ref in annots:
                annot = annot_ref.get_object()
                field_name = annot.get('/T')
                if field_name == 'year':
                    annot[NameObject('/Q')] = NumberObject(1)  # 1 = center align
                    print(f"[PDF DEBUG] Set year field to center alignment")
    
    for page_num, page in enumerate(writer.pages):
        print(f"[PDF DEBUG] Updating page {page_num + 1}")
        writer.update_page_form_field_values(page, merged)
        
        # Add CTC watermark if this is a certified true copy
        if is_ctc:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=letter)
            can.setFont("Helvetica-Bold", 60)
            can.setFillColorRGB(0.3, 0.3, 0.3, alpha=0.15)
            can.saveState()
            can.translate(300, 400)
            can.rotate(45)
            can.drawCentredString(0, 0, "CERTIFIED TRUE COPY")
            can.restoreState()
            can.save()
            packet.seek(0)
            watermark = PdfReader(packet)
            page.merge_page(watermark.pages[0])
        
        # Add CTC watermark if this is a certified true copy
        if is_ctc:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=letter)
            can.setFont("Helvetica-Bold", 60)
            can.setFillColorRGB(0.3, 0.3, 0.3, alpha=0.15)
            can.saveState()
            can.translate(300, 400)
            can.rotate(45)
            can.drawCentredString(0, 0, "CERTIFIED TRUE COPY")
            can.restoreState()
            can.save()
            packet.seek(0)
            watermark = PdfReader(packet)
            page.merge_page(watermark.pages[0])
    
    buf = io.BytesIO()
    writer.write(buf)
    result = buf.getvalue()
    print(f"[PDF DEBUG] Generated PDF size: {len(result)} bytes")
    return result

# ────────────────────────────────────────────────────────────
# SECTION: Semantic → default field builder (per doc type)
# ────────────────────────────────────────────────────────────
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
    # Always fetch captain from database, ignore header value
    captain = _get_barangay_captain_name()
    doc_name = _safe_str(line.get("document_type_name")).lower()

    if "clearance" in doc_name:
        result = {
            "requestor_full_name": subject_full_name,
            "requestor_age": subject_age,
            "requestor_civil_status": subject_civil,
            "requestor_addr": subject_addr,
            "doc_purpose": purpose,
            "date_issued": d, "month_issued": m, "year_issued": y,
            "barangay_issued": barangay, "city_mun_issued": city, "province_issued": province,
            "brgy_captain": captain, "totla_amnt": line_total, "or_number": or_no,
        }
        print(f"[FILL_FIELDS DEBUG] Barangay clearance fields generated: {result}")
        return result

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
        # Get family income from line details
        details = line.get("details") or {}
        family_income_range = _safe_str(details.get("family_income_range") or "")
        
        paid_amt = header.get("paid_amount") or line.get("line_total")
        paid_amt_str = "0" if paid_amt is None or paid_amt == "" or paid_amt == 0 else _safe_str(paid_amt)
        
        return {
            "full_name": subject_full_name, "age": subject_age, "civil_status": subject_civil, "nationality": subject_nat,
            "barangay_name": barangay, "city_municipality": city, "province": province,
            "total_earning": family_income_range or "No data", "purpose": purpose,
            "total_earning": family_income_range or "No data", "purpose": purpose,
            "day": d, "month": m, "year": y,
            "issued_at_brgy": barangay, "issued_at_city_municipality": city, "issued_at_province": province,
            "amnt": paid_amt_str, "official_reciept": or_no or "—",
            "amnt": paid_amt_str, "official_reciept": or_no or "—",
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
            "brgy_captain": captain, "total_amnt": _safe_str(pick(line.get("line_total"), "", allow_zero=True)), "or_number": or_no,
        }

    if "permit" in doc_name:
        event_dt = _safe_str(line.get("event_date_time") or "")
        return {
            "requestor_org": _safe_str(line.get("org_name") or ""), "requestor_name": subject_full_name,
            "requested_event": _safe_str(line.get("event_name") or ""), "event_location": _safe_str(line.get("event_location") or ""),
            "barangay_name": barangay, "brgy_date_time": event_dt,
            "issued_date": d, "issued_month": m, "issued_year": y,
            "barangay_issued": barangay, "cty_mun_issued": city, "province_issued": province,
            "brgy_capt": captain, "total_amnt": _safe_str(pick(line.get("line_total"), "", allow_zero=True)), "or_number": or_no,
        }

    if "residency" in doc_name:
        # Get residency information from line details
        details = line.get("details") or {}
        residency_since_text = _safe_str(details.get("residency_since_text") or "")
        
        # If residency_since_text is empty, try to construct from residency_since_date
        if not residency_since_text:
            residency_date = details.get("residency_since_date")
            if residency_date:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(str(residency_date).replace('Z', '+00:00'))
                    residency_since_text = dt.strftime("%B %Y")
                except Exception as e:
                    print(f"[RESIDENCY DEBUG] Failed to parse residency_since_date: {e}")
                    residency_since_text = ""
        
        paid_amt = header.get("paid_amount") or line.get("line_total")
        paid_amt_str = "0" if paid_amt is None or paid_amt == "" or paid_amt == 0 else _safe_str(paid_amt)
        
        result = {
            "name": subject_full_name,
            "age": subject_age,
            "addr": subject_addr,
            "date_of_residency": residency_since_text or "No data",
            "purpose": purpose,
            "date": d,
            "month": m,
            "year": y,
            "capt": captain,
            "amnt": paid_amt_str,
            "reciept": or_no or "—",
        }
        print(f"[RESIDENCY DEBUG] Generated fields: {result}")
        print(f"[RESIDENCY DEBUG] Details from line: {details}")
        return result

    return {}