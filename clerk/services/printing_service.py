from __future__ import annotations

import io, os, json, datetime as dt
from typing import Any, Dict, List, Optional, Tuple

from django.utils import timezone
from django.conf import settings

from authentication.supabase_client import supabase
from .requests_service import _fetch_bundle  # reuse your existing service
from .subject_service import subject_view
from .pdf_service import (
    _pdf_templates_dir, _get_all_pdf_field_names, _fill_pdf_with_values,
    _choose_template, _safe_str, _fill_fields_for_line,
    BUSINESS_CLEARANCE_FIELD_MAP,
)
from .walkin_service import fetch_business_clearance_fields

BRGY_BUSINESS_DOC_NAME = "BARANGAY BUSINESS CLEARANCE"
BRGY_BUSINESS_PDF_FILE = "barangay-business-clearance.pdf"

def _parse_dt_any(val: Any):
    try:
        if isinstance(val, dt.datetime):
            return val
        if isinstance(val, dt.date) and not isinstance(val, dt.datetime):
            return dt.datetime(val.year, val.month, val.day, tzinfo=timezone.get_current_timezone())
        if isinstance(val, str):
            s = val.strip().replace("Z", "+00:00")
            try:
                return dt.datetime.fromisoformat(s)
            except Exception:
                try:
                    d = dt.date.fromisoformat(s[:10])
                    return dt.datetime(d.year, d.month, d.day, tzinfo=timezone.get_current_timezone())
                except Exception:
                    return None
    except Exception:
        return None
    return None

def friendly_date_text(val: Any) -> Optional[str]:
    d = _parse_dt_any(val)
    if not d:
        return None
    try:
        try:
            d_local = timezone.localtime(d)
        except Exception:
            d_local = d
        return d_local.strftime("%B %d, %Y")
    except Exception:
        return None

def apply_pdf_field_mapping(doc_name: str, field_names: List[str], values: Dict[str, Any], include_debug: bool=False) -> Dict[str, Any]:
    nm = (doc_name or "").strip().upper()
    if nm == BRGY_BUSINESS_DOC_NAME:
        advice = {
          "applicant_nationality": "Join person.nationality_id → nationality.nationality_name.",
          "applicant_full_name":   "From person(first_name,last_name) of subject/requester.",
          "applicant_age":         "Compute from person.birthdate.",
          "business_name_style":   "From business.business_name.",
          "business_address":      "From business.address_id → address(street,purok_sitio,barangay,city).",
          "capital_invested":      "From business.capital_invested.",
          "gross_sales_prev_year": "From business.prev_yr_total_gross_sales.",
          "lines_of_business_1":   "Split business.business_nature by comma (1st).",
          "lines_of_business_2":   "Split business.business_nature by comma (2nd).",
          "lines_of_business_3":   "Split business.business_nature by comma (3rd).",
          "lines_of_business_4":   "Split business.business_nature by comma (4th).",
          "lines_of_business_5":   "Split business.business_nature by comma (5th).",
          "paid_amount":           "From payments.latest_amount or payments.amount.",
        }
        mapped: Dict[str, Any] = {}
        for skey, pdf_field in BUSINESS_CLEARANCE_FIELD_MAP.items():
            if pdf_field not in field_names:
                continue
            val = values.get(skey)
            if val is None or str(val).strip() == "":
                if include_debug:
                    mapped.setdefault(pdf_field, pdf_field)
                print(f"[PRINT MAP] {nm}: {skey} → {pdf_field} = {pdf_field!r} [MISSING→printing field name]")
                if skey in advice:
                    print(f"[PRINT ADVICE] Missing '{skey}'. How to get it: {advice[skey]}")
            else:
                mapped[pdf_field] = val
                print(f"[PRINT MAP] {nm}: {skey} → {pdf_field} = {val!r}")
        return mapped

    # For barangay clearance and other documents, return values directly mapped to field names
    mapped = {}
    for fn in field_names:
        val = values.get(fn)
        if val is not None:
            mapped[fn] = val
            print(f"[PRINT MAP] {nm}: {fn} = {val!r}")
        else:
            print(f"[PRINT MAP] {nm}: {fn} = MISSING")
    return mapped

def process_printing(doc_request_id: int, include_debug: bool=False) -> Tuple[bytes, str, str, Dict[str, str]]:
    """
    Encapsulates the original mark_for_printing logic and returns:
      (content_bytes, content_type, filename, extra_headers)
    Raises exceptions on fatal errors (so the view can message/redirect).
    """
    data: Dict[str, Any] = _fetch_bundle(doc_request_id)
    header = data.get("header", {}) or {}
    lines: List[Dict[str, Any]] = data.get("lines", []) or []
    payments = data.get("payments", {}) or {}

    # expose receipt info to PDFs (preserve original logic)
    header["or_number"] = (
        payments.get("latest_or_number")
        or payments.get("or_number")
        or _safe_str(header.get("or_number"))
    )

    line_total = sum(float(line.get("line_total", 0) or 0) for line in lines)
    header["paid_amount"] = line_total or payments.get("amount")
    header["paid_date"]   = payments.get("latest_paid_at") or payments.get("paid_at") or payments.get("latest_or_time")
    print("[PRINT DEBUG] payments keys (sample):", list(payments.keys())[:20])
    print("[PRINT DEBUG] header snapshot:", json.dumps({k: header.get(k) for k in ["request_code","or_number","paid_amount","paid_date"]}, indent=2, default=str))

    outputs: List[tuple[str, bytes]] = []
    debug_items: List[Dict[str, Any]] = []
    base_dir = _pdf_templates_dir()

    for idx, line in enumerate(lines, start=1):
        doc_name = _safe_str(line.get("document_type_name") or f"doc-{idx}")

        template_file = _choose_template(doc_name, False)
        det = (line.get("details") or {})
        doc_upper = doc_name.strip().upper()
        is_business_clearance = (doc_upper == BRGY_BUSINESS_DOC_NAME or "CTC" in doc_upper and "BUSINESS CLEARANCE" in doc_upper)
        if is_business_clearance or det.get("template_override") == BRGY_BUSINESS_PDF_FILE:
            is_ctc = "CTC" in doc_upper or det.get("is_certified_true_copy") or line.get("is_certified_true_copy") or header.get("is_certified_true_copy")
            template_file = "barangay-ctc.pdf" if is_ctc else BRGY_BUSINESS_PDF_FILE
            print(f"[PRINT DEBUG] doc='{doc_name}' (from='{line.get('document_type_name')}') -> template='{template_file}' (CTC={is_ctc})")
        template_path = os.path.join(base_dir, template_file)

        if not os.path.exists(template_path):
            alt = os.path.join(settings.BASE_DIR, "clerk", "pdf_templates", template_file)
            if os.path.exists(alt):
                template_path = alt
            else:
                print(json.dumps({
                    "doc_index": idx, "doc_name": doc_name, "template_file": template_file,
                    "template_path": template_path, "exists": False, "reason": "Template not found"
                }, indent=2))
                continue

        base_values = _fill_fields_for_line(header, line)
        detail_values = (line.get("details") or {})
        combined_values = {**detail_values, **base_values}
        print(f"[PRINT DEBUG] Base values from _fill_fields_for_line: {base_values}")
        print(f"[PRINT DEBUG] Detail values: {detail_values}")
        print(f"[PRINT DEBUG] Combined values: {combined_values}")

        try:
            _subj = subject_view(header, line)
            combined_values.setdefault("applicant_full_name", _safe_str(_subj.get("full_name")))
            combined_values.setdefault("applicant_age", _safe_str(_subj.get("age")))
            combined_values.setdefault("applicant_nationality", _safe_str(_subj.get("nationality")))
        except Exception as e:
            print(f"[PRINT DEBUG] subject fallbacks failed: {e}")

        combined_values["numberfour"] = header.get("request_code")

        created_any = header.get("created_at") or header.get("created_ts") or header.get("date_created")
        friendly_applied = friendly_date_text(created_any)
        combined_values["numberfive"] = friendly_applied or _safe_str(created_any)

        combined_values.setdefault("numbersixteen", header.get("captain_name") or "Lourdes R. Ramirez")
        combined_values.setdefault("year_issued", timezone.localtime().strftime("%Y"))

        combined_values.setdefault("paid_amount", header.get("paid_amount"))
        if header.get("paid_date"):
            combined_values["paid_date"] = friendly_date_text(header.get("paid_date"))
        else:
            combined_values.setdefault("paid_date", None)
        combined_values.setdefault("or_number", header.get("or_number"))

        doc_upper = doc_name.strip().upper()
        if doc_upper == BRGY_BUSINESS_DOC_NAME or ("CTC" in doc_upper and "BUSINESS CLEARANCE" in doc_upper):
            bc_keys = ["business_name_style","business_address","capital_invested","gross_sales_prev_year"]
            needs_enrich = any(not _safe_str(combined_values.get(k)).strip() for k in bc_keys)
            if needs_enrich:
                bid = header.get("business_id")
                if not bid:
                    try:
                        r = (
                            supabase.table("document_request")
                            .select("business_id")
                            .eq("doc_request_id", doc_request_id)
                            .limit(1)
                            .execute()
                        )
                        bid = ((r.data or [{}])[0] or {}).get("business_id")
                    except Exception as e:
                        print(f"[PRINT DEBUG] could not fetch business_id for request {doc_request_id}: {e}")
                subj_pid = header.get("subject_person_id") or header.get("requested_by_person_id")
                if bid:
                    try:
                        bc_enrich = fetch_business_clearance_fields(int(bid), int(subj_pid) if subj_pid else None)
                        combined_values = {**bc_enrich, **combined_values}
                        print("[PRINT DEBUG] Applied business fallback from DB:",
                              json.dumps({k: combined_values.get(k) for k in bc_keys}, default=str))
                    except Exception as e:
                        print(f"[PRINT DEBUG] business fallback failed: {e}")

        field_names = _get_all_pdf_field_names(template_path)
        values_mapped = apply_pdf_field_mapping(doc_name, field_names, combined_values, include_debug)
        print(f"[PRINT DEBUG] Values mapped for {doc_name}: {values_mapped}")
        print(f"[PRINT DEBUG] Field names found: {field_names}")
        print(f"[PRINT DEBUG] Combined values keys: {list(combined_values.keys())}")

        # Use actual mapped values instead of test values
        merged = values_mapped
        print(f"[CRITICAL DEBUG] Template: {template_path}")
        print(f"[CRITICAL DEBUG] Template exists: {os.path.exists(template_path)}")
        print(f"[CRITICAL DEBUG] Field names extracted: {field_names}")
        print(f"[CRITICAL DEBUG] Number of fields: {len(field_names)}")
        print(f"[CRITICAL DEBUG] Merged dict for PDF: {merged}")
        print(f"[CRITICAL DEBUG] Will attempt to fill {len(merged)} fields")
        missing = [n for n in field_names if n not in values_mapped or str(values_mapped.get(n) or "").strip() == ""]

        print(json.dumps({
            "doc_index": idx,
            "doc_name": doc_name,
            "template_file": template_file,
            "template_path": template_path,
            "field_count": len(field_names),
            "missing_count": len(missing),
            "missing_fields": missing,
            "line_details_keys": list((line.get("details") or {}).keys()),
            "combined_values_sample": {k: combined_values.get(k) for k in list(combined_values)[:15]},
            "values_mapped_sample": {k: values_mapped.get(k) for k in list(values_mapped)[:15]},
            "sample_values_written": {k: merged[k] for k in field_names[:10]},
        }, indent=2, default=str))

        try:
            print(f"[CRITICAL DEBUG] Attempting to fill PDF with {len(merged)} values")
            pdf_bytes = _fill_pdf_with_values(template_path, merged)
            print(f"[CRITICAL DEBUG] PDF filled successfully for {doc_name}, size: {len(pdf_bytes)} bytes")
        except Exception as e:
            print(f"[CRITICAL DEBUG] PDF filling FAILED for {doc_name}: {str(e)}")
            import traceback
            print(f"[CRITICAL DEBUG] Full error: {traceback.format_exc()}")
            with open(template_path, "rb") as f:
                pdf_bytes = f.read()
            print(f"[CRITICAL DEBUG] Using original PDF, size: {len(pdf_bytes)} bytes")

        safe_name = doc_name.lower().replace(" ", "-")
        out_name = f"{header.get('request_code','REQ')}-{safe_name}.pdf"
        outputs.append((out_name, pdf_bytes))
        debug_items.append({
            "output_filename": out_name,
            "doc_name": doc_name,
            "template_file": template_file,
            "template_path": template_path,
            "field_names": field_names,
            "values_written": merged,
        })

    if not outputs:
        raise RuntimeError("No PDF templates found. Check your pdf_templates folder and filenames.")

    # Single PDF
    if len(outputs) == 1 and not include_debug:
        fname, bytes_ = outputs[0]
        headers = {
            "X-Debug-Doc-Name": debug_items[0].get("doc_name","") if debug_items else "",
            "X-Debug-Template": debug_items[0].get("template_file","") if debug_items else "",
            "X-Debug-Fields": str(len(debug_items[0].get("field_names",[]))) if debug_items else "0",
        }
        return bytes_, "application/pdf", fname, headers

    # ZIP
    zbuf = io.BytesIO()
    import zipfile
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, b in outputs:
            zf.writestr(fname, b)
        if include_debug and debug_items:
            debug_payload = {
                "request_code": header.get("request_code"),
                "doc_request_id": doc_request_id,
                "generated_at": timezone.localtime().isoformat(),
                "items": debug_items,
            }
            zf.writestr(f"DEBUG-{header.get('request_code','REQ')}.json", json.dumps(debug_payload, indent=2))

    req_code = header.get("request_code", "REQ")
    return zbuf.getvalue(), "application/zip", f"{req_code}-documents.zip", {}