from typing import Optional, Tuple
import json

from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException
from src.infra.repositories.maternal_report_repository import MaternalReportRepository
from src.infra.utilities.pdf_generator import PdfGenerator
from src.infra.utilities.age_calculator import AgeCalculator
import os

import logging

logger = logging.getLogger(__name__)
from src.app.utility.maternal_report_helpers import MaternalReportHelpers
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER


# Paragraph style for table cells: wrap long text and center contents
TABLE_PARAGRAPH_STYLE = ParagraphStyle(
    "TableBody",
    fontName="Times-Roman",
    fontSize=10,
    leading=12,
    alignment=TA_CENTER,
)


def _fmt(value) -> str:
    """Format a value for display in the PDF: return 'N/A' for None or
    empty strings, otherwise return the string representation.
    Keeps numeric zero (0) intact.
    """
    if value is None:
        return "N/A"
    if isinstance(value, str):
        s = value.strip()
        return s if s != "" else "N/A"
    return str(value)


class MaternalReportService:
    """Service to generate maternal health summary reports.

    The service fetches data via the repository and uses the PdfGenerator to
    produce a printable PDF (bytes) suitable for printing or sharing.
    """

    def __init__(self, repository: MaternalReportRepository, pdf_generator: Optional[PdfGenerator] = None):
        self._repo = repository
        self._pdf = pdf_generator or PdfGenerator()

    def generate_maternal_summary_pdf(
        self,
        maternal_record_id: int,
        header_lines: Optional[list] = None,
        watermark: Optional[str] = None,
        left_image: Optional[str] = None,
        right_image: Optional[str] = None,
        generated_by_name: Optional[str] = None,
        generated_by_role: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Return PDF bytes for the maternal health summary report for a record id.

        The view (API) may supply optional header_lines (list of (text,size)),
        watermark text, and left/right image paths. If any are not provided,
        this service will fall back to sensible defaults defined here.
        """
        try:
            payload = self._repo.assemble_report_payload(maternal_record_id)

            # Ensure the maternal health record exists. If the repository
            # returned no patient info then the requested maternal_record_id
            # does not exist (or has been deleted); raise an error so callers
            # can handle it explicitly.
            if not payload.get("patient_info"):
                logger.error("Maternal health record %s not found", maternal_record_id)
                raise MaternalHealthRecordException(f"Maternal health record not found")

            # Build sections in an order matching requested report structure
            sections = []

            # small helpers used to sanitize and compute values for the PDF
            # (extracted to MaternalReportHelpers static methods)

            # Patient Info
            p = payload.get("patient_info") or {}
            # compute age readable and also numeric age when available
            age_readable = _fmt(AgeCalculator.get_readable_age_from_payload(p))
            try:
                numeric_age = int(p.get('age')) if p.get('age') is not None else None
            except Exception:
                numeric_age = None

            def age_group_for_years(y: Optional[int]) -> str:
                if y is None:
                    return "N/A"
                if y < 15:
                    return "<15"
                if 15 <= y <= 19:
                    return "15-19"
                if 20 <= y <= 34:
                    return "20-34"
                if 35 <= y <= 49:
                    return "35-49"
                return "50+"

            patient_lines = [
                f"Family #: {_fmt(p.get('family_num'))} | UFC: {_fmt(p.get('ufc_num'))}",
                f"Name: {_fmt(p.get('first_name'))} {_fmt(p.get('middle_name'))} {_fmt(p.get('last_name'))}",
                f"Date of Birth: {_fmt(p.get('birthdate'))}",
                f"Age: {age_readable}",
                f"Age Group: {_fmt(age_group_for_years(numeric_age))}",
                f"Address: {_fmt(p.get('address'))}",
                f"Husband: {_fmt(p.get('husband_full_name'))}",
                f"Patient Occupation: {_fmt(p.get('patient_occupation'))}",
            ]

            # BMI calculation: compute numeric BMI if possible, place after Height
            weight_val = p.get('weight')
            height_val = p.get('height')
            bmi_value = MaternalReportHelpers.compute_bmi(weight_val, height_val)
            weight_display = str(weight_val) if weight_val is not None else None
            height_display = str(height_val) if height_val is not None else None
            bmi_display = bmi_value or None
            patient_lines.append(f"Weight: {_fmt(weight_display)} kg | Height: {_fmt(height_display)} m | BMI: {_fmt(bmi_display)}")
            patient_lines.append(f"BMI Category: {_fmt(p.get('bmi_status_name'))}")
            sections.append({"heading": "Patient Info", "content": "<br/>".join(patient_lines)})

            # Pregnancy Summary
            ps = payload.get("pregnancy_summary") or {}
            preg_lines = [
                f"Gravida: {_fmt(ps.get('gravida'))}",
                f"Para: {_fmt(ps.get('para'))}",
                f"Full Term: {MaternalReportHelpers.bool_to_yesno(ps.get('is_fullterm', None))}",
                f"Pre Term: {MaternalReportHelpers.bool_to_yesno(ps.get('is_preterm', None))}",
                f"Trimester: {_fmt(ps.get('trimester_stage_name'))}",
                f"LMP: {_fmt(ps.get('lmp'))}",
                f"EDC: {_fmt(ps.get('edc'))}",
                f"Transferred: {MaternalReportHelpers.bool_to_yesno(ps.get('is_transferred', None))}",
            ]
            sections.append({"heading": "Pregnancy Summary", "content": "<br/>".join(preg_lines)})

            # Medical & Obstetric History
            med = payload.get("medical_history") or {}
            obst = payload.get("obstetric_history") or {}
            med_lines = [
                f"Previous Illnesses: {_fmt(med.get('previous_illness'))}",
                f"Previous Hospitalization: {_fmt(med.get('previous_hospitalization'))}",
                f"Previous Pregnancy Complications: {_fmt(med.get('previous_preg_complication'))}",
            ]
            sections.append({"heading": "Medical History", "content": "<br/>".join(med_lines)})
            obst_lines = [
                f"Children Born Alive: {_fmt(obst.get('num_children_born_alive'))}",
                f"Children Living: {_fmt(obst.get('num_children_living'))}",
                f"Abortions: {_fmt(obst.get('num_abortion'))}",
                f"Stillbirths: {_fmt(obst.get('num_stillbirth'))}",
                f"Large Babies: {_fmt(obst.get('num_large_babies'))}",
                f"Diabetes: {MaternalReportHelpers.bool_to_yesno(obst.get('has_diabetes', None))}",
            ]
            sections.append({"heading": "Obstetric History", "content": "<br/>".join(obst_lines)})

            # Previous pregnancies (expanded)
            prev = payload.get('previous_pregnancy') or {}
            prev_lines = [
                f"Date of Delivery: {_fmt(prev.get('date_of_deliveries'))}",
                f"Outcome: {_fmt(prev.get('outcome'))}",
                f"Type of Delivery: {_fmt(prev.get('delivery_type_name') or prev.get('delivery_type_id'))}",
                f"Baby Weight: {_fmt(prev.get('baby_weight'))}",
                f"Gender: {_fmt(prev.get('baby_sex'))}",
                f"Ballard Score: {_fmt(prev.get('ballard_score'))}",
                f"Apgar Score: {_fmt(prev.get('apgar_score'))}",
            ]
            sections.append({"heading": "Previous Pregnancies", "content": "<br/>".join(prev_lines)})

            # Lab Results Summary (table) - do not expose internal ID numbers
            labs = payload.get("lab_results") or []
            lab_table = [["Test Type", "Result", "Date Tested"]]
            for l in labs:
                # Prefer the lab test type name (new field from repository). If both
                # the type and the original test name exist, show the type with
                # the original name in parentheses so callers see both pieces.
                raw_test_name = l.get("test_name") or l.get("lab_test_name") or ""
                type_name = l.get("lab_test_type_name") or ""
                if type_name and raw_test_name:
                    display_name = f"{type_name} ({raw_test_name})"
                elif type_name:
                    display_name = type_name
                else:
                    display_name = raw_test_name

                # attachments count
                attachments = l.get('result_img_path')
                attach_count = None
                if attachments:
                    try:
                        parsed = json.loads(attachments)
                        if isinstance(parsed, list):
                            attach_count = len(parsed)
                        else:
                            attach_count = 1
                    except Exception:
                        attach_count = 1

                result_display = l.get("result", "")
                if attach_count:
                    result_display = f"{_fmt(result_display)} | {attach_count} Attachments"

                lab_table.append([display_name, result_display, l.get("date_tested", "")])
            # wrap lab table cells in Paragraphs so long text wraps and is centered
            lab_table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in lab_table]
            sections.append({"heading": "Lab Results Summary", "content": lab_table_wrapped})

            # Tetanus toxoid mapping
            vax = payload.get("vaccination_records") or []
            tt_map = {row.get('tt_type_name'): row.get('date_given') for row in vax}
            tt_rows = [
                ["TT1", _fmt(tt_map.get('TT1'))],
                ["TT2", _fmt(tt_map.get('TT2'))],
                ["TT3", _fmt(tt_map.get('TT3'))],
                ["TT4", _fmt(tt_map.get('TT4'))],
                ["TT5", _fmt(tt_map.get('TT5'))],
                ["FIM", _fmt(tt_map.get('FIM'))],
            ]
            vax_table = [["Vaccine", "Date Given"]] + tt_rows
            vax_table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in vax_table]
            sections.append({"heading": "Tetanus Toxoid Given Dates", "content": vax_table_wrapped})

            # Micronutrients
            micron = payload.get("micronutrients") or {}
            micron_lines = [
                f"Iron w/ Folic Acid Start: {_fmt(micron.get('iron_start_date'))}",
                f"Iron w/ Folic Acid Completed: {_fmt(micron.get('iron_end_date'))}",
                f"Deworming Given: {_fmt(micron.get('deworming_given_date'))}",
            ]
            sections.append({"heading": "Micronutrient Intake", "content": "<br/>".join(micron_lines)})

            # Checklist findings — explicit mapping
            checklist = payload.get("checklist_findings") or []
            expected_checks = [
                'PREECLAMPSIA', 'ABNORMAL VAGINAL DISCHARGES', 'VAGINAL BLEEDING',
                'CHILLS & FEVER', 'DIFFICULTY IN BREATHING', 'VARICOSITIES', 'ABDOMINAL PAIN'
            ]
            check_names = {c.get('checklist_name'): True for c in checklist}
            check_lines = [f"{name}: {('Yes' if check_names.get(name) else 'N/A')}" for name in expected_checks]
            sections.append({"heading": "Checklist Findings", "content": "<br/>".join(check_lines)})

            # Plans - place of delivery
            plan = payload.get('plan_and_baseline') or {}
            plan_lines = [f"Planned Place of Delivery: {_fmt(plan.get('place_of_delivery_plan'))}"]
            sections.append({"heading": "Plans", "content": "<br/>".join(plan_lines)})

            # Prenatal follow-up entries (ANC rows)
            anc_rows = payload.get('anc_rows') or []
            if anc_rows:
                anc_table = [["AOG (days)", "AOG (weeks)", "Weight (kg)", "BP Systolic", "BP Diastolic", "Findings", "Notes"]]
                for r in anc_rows:
                    anc_table.append([
                        _fmt(r.get('aog_days')),
                        _fmt(r.get('aog_weeks')),
                        _fmt(r.get('weight_kg')),
                        _fmt(r.get('bp_systolic')),
                        _fmt(r.get('bp_diastolic')),
                        _fmt(r.get('leopolds_findings')),
                        _fmt(r.get('notes')),
                    ])
                anc_table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in anc_table]
                sections.append({"heading": "Prenatal Follow-up Entries", "content": anc_table_wrapped})
            else:
                sections.append({"heading": "Prenatal Follow-up Entries", "content": "N/A"})

            # Build document title
            name = p.get('first_name','')
            last = p.get('last_name','')
            title = f"Maternal Health Summary Report - {name} {last}".strip()
            # Compose defaults; allow caller to override via parameters
            default_header_lines = [
                ("Republic of the Philippines", 14),
                ("Barangay Health Center", 14),
                ("BARANGAY SEÑOR SANTO NIÑO", 14),
                ("032 Legaspi Street, Cebu City", 11),
            ]

            header_lines_to_use = header_lines or default_header_lines

            default_watermark = "CONFIDENTIAL HEALTH INFORMATION"
            watermark_to_use = watermark or default_watermark

            left_img_to_use = None
            right_img_to_use = None
            # Only use images if the caller explicitly provided them. Do not
            # fall back to the default image here — the view or caller will
            # handle defaulting logic if desired.
            left_img_to_use = MaternalReportHelpers.resolve_image(left_image) if left_image else None
            right_img_to_use = MaternalReportHelpers.resolve_image(right_image) if right_image else None

            pdf_bytes = self._pdf.generate(
                title=title,
                header_lines=header_lines_to_use,
                header_color="#002060",
                left_image_path=left_img_to_use,
                right_image_path=right_img_to_use,
                watermark_text=watermark_to_use,
                sections=sections,
                additional_signatory_name=generated_by_name,
                additional_signatory_role=generated_by_role,
            )
            # Build filename in service layer: lastname_firstname_id (sanitized)
            first = (p.get('first_name') or '').strip()
            last = (p.get('last_name') or '').strip()

            def _sanitize(s: str) -> str:
                # keep alphanumerics and underscores
                return ''.join(ch for ch in s.replace(' ', '_') if (ch.isalnum() or ch == '_')).lower() or 'unknown'

            fname = f"{_sanitize(last)}_{_sanitize(first)}_{maternal_record_id}.pdf"

            return pdf_bytes, fname

        except Exception:
            logger.exception("Failed to generate maternal summary PDF for mhr %s", maternal_record_id)
            raise
