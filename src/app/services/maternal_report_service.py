from typing import Optional, Tuple
import json

from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException
from src.infra.repositories.maternal_report_repository import MaternalReportRepository
from src.infra.repositories.queries.maternal_reports_query import MaternalReportsQuery
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

    def __init__(self, repository: MaternalReportRepository, pdf_generator: Optional[PdfGenerator] = None, reports_query: Optional[MaternalReportsQuery] = None):
        self._repo = repository
        self._pdf = pdf_generator or PdfGenerator()
        self._reports_query = reports_query

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

    # ===== ANALYTICS REPORT METHODS =====

    def _default_header_lines(self) -> list:
        """Return default header lines for analytics reports."""
        return [
            ("Republic of the Philippines", 14),
            ("Barangay Health Center", 14),
            ("BARANGAY SEÑOR SANTO NIÑO", 14),
            ("Maternal Health Analytics Report", 11),
        ]

    def generate_monthly_visit_compliance_pdf(
        self,
        year: int,
        month: int,
        header_lines: Optional[list] = None,
        watermark: Optional[str] = None,
        left_image: Optional[str] = None,
        right_image: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate Monthly Maternal Visit Compliance Dashboard PDF."""
        if not self._reports_query:
            raise ValueError("MaternalReportsQuery not injected into service")
        
        data = self._reports_query.get_monthly_visit_compliance(year, month)
        
        sections = []
        
        # Visit Summary
        vs = data.get('visit_summary') or {}
        vs_lines = [
            f"Total Scheduled Visits: {_fmt(vs.get('total_scheduled'))}",
            f"Completed Visits: {_fmt(vs.get('completed_visits'))}",
            f"Missed Visits: {_fmt(vs.get('missed_visits'))}",
            f"Delayed Visits: {_fmt(vs.get('delayed_visits'))}",
            f"Average Delay (days): {_fmt(vs.get('avg_delay_days'))}",
            f"Compliance Rate: {_fmt(vs.get('compliance_rate'))}%",
        ]
        sections.append({"heading": "Visit Summary", "content": "<br/>".join(vs_lines)})
        
        # High Risk Cases
        hrc = data.get('high_risk_cases') or []
        if hrc:
            hrc_table = [["Mother Name", "Risk Count", "Risk Categories", "Missed Visits"]]
            for case in hrc:
                hrc_table.append([
                    Paragraph(_fmt(case.get('mother_name')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(case.get('risk_count')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(case.get('risk_categories')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(case.get('missed_visits')), TABLE_PARAGRAPH_STYLE),
                ])
            sections.append({"heading": "High Risk Cases", "content": hrc_table})
        
        # Mother Compliance
        mc = data.get('mother_compliance') or []
        if mc:
            mc_table = [["Mother Name", "Total Visits", "Completed", "Missed", "Compliance %"]]
            for mother in mc[:20]:  # Top 20
                mc_table.append([
                    Paragraph(_fmt(mother.get('mother_name')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('total_visits')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('completed')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('missed')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('compliance_pct')), TABLE_PARAGRAPH_STYLE),
                ])
            sections.append({"heading": "Mother Compliance (Top 20)", "content": mc_table})
        
        header_lines_to_use = header_lines or self._default_header_lines()
        left_img_to_use = MaternalReportHelpers.resolve_image(left_image) if left_image else None
        right_img_to_use = MaternalReportHelpers.resolve_image(right_image) if right_image else None

        pdf_bytes = self._pdf.generate(
            title=f"Monthly Visit Compliance Report - {year}/{month:02d}",
            header_lines=header_lines_to_use,
            left_image_path=left_img_to_use,
            right_image_path=right_img_to_use,
            watermark_text=watermark,
            sections=sections,
        )

        return pdf_bytes, f"maternal_visit_compliance_{year}_{month:02d}.pdf"

    def generate_monthly_risk_indicator_pdf(
        self,
        year: int,
        month: int,
        header_lines: Optional[list] = None,
        watermark: Optional[str] = None,
        left_image: Optional[str] = None,
        right_image: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate Monthly Maternal Risk Indicator Summary PDF."""
        if not self._reports_query:
            raise ValueError("MaternalReportsQuery not injected into service")
        
        data = self._reports_query.get_monthly_risk_indicator_summary(year, month)
        
        sections = []
        
        # Risk Summary
        rs = data.get('risk_summary') or {}
        rs_lines = [
            f"Total Mothers: {_fmt(rs.get('total_mothers'))}",
            f"Underweight: {_fmt(rs.get('underweight_count'))} ({_fmt(rs.get('underweight_pct'))}%)",
            f"Teen Pregnancy: {_fmt(rs.get('teen_pregnancy_count'))} ({_fmt(rs.get('teen_pregnancy_pct'))}%)",
            f"Diabetes: {_fmt(rs.get('diabetes_count'))}",
            f"Prior Abortion: {_fmt(rs.get('prior_abortion_count'))}",
            f"Prior Stillbirth: {_fmt(rs.get('prior_stillbirth_count'))}",
            f"Hypertension: {_fmt(rs.get('hypertension_count'))}",
        ]
        sections.append({"heading": "Risk Summary", "content": "<br/>".join(rs_lines)})
        
        # Risk Category Breakdown
        rcb = data.get('risk_category_breakdown') or []
        if rcb:
            rcb_table = [["Risk Category", "Mothers Affected", "Percentage"]]
            for cat in rcb:
                rcb_table.append([
                    Paragraph(_fmt(cat.get('risk_category_name')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(cat.get('mothers_affected')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(cat.get('percentage')), TABLE_PARAGRAPH_STYLE),
                ])
            sections.append({"heading": "Risk Category Breakdown", "content": rcb_table})
        
        # High Risk Mothers
        hrm = data.get('high_risk_mothers') or []
        if hrm:
            hrm_table = [["Mother Name", "BMI Status", "Age", "Risk Categories", "Risk Score"]]
            for mother in hrm:
                hrm_table.append([
                    Paragraph(_fmt(mother.get('mother_name')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('bmi_status_name')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('age')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('risk_categories')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('risk_score')), TABLE_PARAGRAPH_STYLE),
                ])
            sections.append({"heading": "High Risk Mothers", "content": hrm_table})
        
        header_lines_to_use = header_lines or self._default_header_lines()
        left_img_to_use = MaternalReportHelpers.resolve_image(left_image) if left_image else None
        right_img_to_use = MaternalReportHelpers.resolve_image(right_image) if right_image else None

        pdf_bytes = self._pdf.generate(
            title=f"Monthly Risk Indicator Report - {year}/{month:02d}",
            header_lines=header_lines_to_use,
            left_image_path=left_img_to_use,
            right_image_path=right_img_to_use,
            watermark_text=watermark,
            sections=sections,
        )

        return pdf_bytes, f"maternal_risk_indicator_{year}_{month:02d}.pdf"

    def generate_monthly_immunization_supplement_pdf(
        self,
        year: int,
        month: int,
        header_lines: Optional[list] = None,
        watermark: Optional[str] = None,
        left_image: Optional[str] = None,
        right_image: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate Monthly Immunization & Supplement Adherence PDF."""
        if not self._reports_query:
            raise ValueError("MaternalReportsQuery not injected into service")
        
        data = self._reports_query.get_monthly_immunization_supplement_adherence(year, month)
        
        sections = []
        
        # TT Vaccine Status
        tts = data.get('tt_vaccine_status') or []
        if tts:
            tts_table = [["TT Type", "Mothers Received", "Coverage %"]]
            for vaccine in tts:
                tts_table.append([
                    Paragraph(_fmt(vaccine.get('tt_type_name')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(vaccine.get('mothers_received')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(vaccine.get('coverage_pct')), TABLE_PARAGRAPH_STYLE),
                ])
            sections.append({"heading": "TT Vaccine Status", "content": tts_table})
        
        # Micronutrient Summary
        ms = data.get('micronutrient_summary') or {}
        ms_lines = [
            f"Iron Started: {_fmt(ms.get('iron_started'))}",
            f"Iron Completed: {_fmt(ms.get('iron_completed'))}",
            f"Deworming Given: {_fmt(ms.get('deworming_given'))}",
            f"Iron Completion Rate: {_fmt(ms.get('iron_completion_rate'))}%",
        ]
        sections.append({"heading": "Micronutrient Summary", "content": "<br/>".join(ms_lines)})
        
        # Adherence by Mother
        abm = data.get('adherence_by_mother') or []
        if abm:
            abm_table = [["Mother Name", "TT Doses", "Iron Status", "Deworming", "Adherence Level"]]
            for mother in abm[:30]:  # Top 30
                abm_table.append([
                    Paragraph(_fmt(mother.get('mother_name')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('tt_doses_received')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('iron_status')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('deworming_status')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('adherence_level')), TABLE_PARAGRAPH_STYLE),
                ])
            sections.append({"heading": "Adherence by Mother (Top 30)", "content": abm_table})
        
        header_lines_to_use = header_lines or self._default_header_lines()
        left_img_to_use = MaternalReportHelpers.resolve_image(left_image) if left_image else None
        right_img_to_use = MaternalReportHelpers.resolve_image(right_image) if right_image else None

        pdf_bytes = self._pdf.generate(
            title=f"Monthly Immunization & Supplement Report - {year}/{month:02d}",
            header_lines=header_lines_to_use,
            left_image_path=left_img_to_use,
            right_image_path=right_img_to_use,
            watermark_text=watermark,
            sections=sections,
        )

        return pdf_bytes, f"maternal_immunization_supplement_{year}_{month:02d}.pdf"

    def generate_trimester_health_outcome_pdf(
        self,
        year: int,
        trimester: int,
        header_lines: Optional[list] = None,
        watermark: Optional[str] = None,
        left_image: Optional[str] = None,
        right_image: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate Trimester Health Outcome Trajectory PDF."""
        if not self._reports_query:
            raise ValueError("MaternalReportsQuery not injected into service")
        
        data = self._reports_query.get_trimester_health_outcome_trajectory(year, trimester)
        
        sections = []
        
        # Weight Trajectory (aggregate summary)
        wt_list = data.get('weight_trajectory') or []
        if wt_list:
            wt_table = [["Mother ID", "Visit Count", "Avg Weight", "Weight Gain", "Gain Status"]]
            for wt in wt_list[:20]:
                wt_table.append([
                    Paragraph(_fmt(wt.get('maternal_record_id')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(wt.get('visit_count')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(wt.get('avg_weight')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(wt.get('weight_gain')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(wt.get('gain_status')), TABLE_PARAGRAPH_STYLE),
                ])
            sections.append({"heading": "Weight Trajectory (Top 20)", "content": wt_table})
        
        # BP Stability
        bp_list = data.get('bp_stability') or []
        if bp_list:
            bp_table = [["Mother ID", "Avg Systolic", "Avg Diastolic", "Max Systolic", "Hypertensive Readings", "BP Status"]]
            for bp in bp_list[:20]:
                bp_table.append([
                    Paragraph(_fmt(bp.get('maternal_record_id')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(bp.get('avg_systolic')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(bp.get('avg_diastolic')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(bp.get('max_systolic')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(bp.get('hypertensive_readings')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(bp.get('bp_status')), TABLE_PARAGRAPH_STYLE),
                ])
            sections.append({"heading": "BP Stability (Top 20)", "content": bp_table})
        
        # Mother Trajectory
        mt_list = data.get('mother_trajectory') or []
        if mt_list:
            mt_table = [["Mother Name", "Trimester", "Weight Gain", "Gain Status", "Avg BP", "BP Status", "Visits"]]
            for mt in mt_list[:20]:
                avg_bp = f"{_fmt(mt.get('avg_systolic'))}/{_fmt(mt.get('avg_diastolic'))}"
                mt_table.append([
                    Paragraph(_fmt(mt.get('mother_name')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mt.get('trimester_stage_name')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mt.get('weight_gain')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mt.get('gain_status')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(avg_bp, TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mt.get('bp_status')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mt.get('visits_this_trimester')), TABLE_PARAGRAPH_STYLE),
                ])
            sections.append({"heading": "Mother Trajectory (Top 20)", "content": mt_table})
        
        header_lines_to_use = header_lines or self._default_header_lines()
        left_img_to_use = MaternalReportHelpers.resolve_image(left_image) if left_image else None
        right_img_to_use = MaternalReportHelpers.resolve_image(right_image) if right_image else None

        pdf_bytes = self._pdf.generate(
            title=f"Trimester {trimester} Health Outcome Report - {year}",
            header_lines=header_lines_to_use,
            left_image_path=left_img_to_use,
            right_image_path=right_img_to_use,
            watermark_text=watermark,
            sections=sections,
        )

        return pdf_bytes, f"maternal_trimester_outcome_{year}_T{trimester}.pdf"

    def generate_trimester_complication_referral_pdf(
        self,
        year: int,
        trimester: int,
        header_lines: Optional[list] = None,
        watermark: Optional[str] = None,
        left_image: Optional[str] = None,
        right_image: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate Trimester Complication & Referral Analytics PDF."""
        if not self._reports_query:
            raise ValueError("MaternalReportsQuery not injected into service")
        
        data = self._reports_query.get_trimester_complication_referral_analytics(year, trimester)
        
        sections = []
        
        # Complication Summary
        cs = data.get('complication_summary') or []
        if cs:
            cs_table = [["Complication Type", "Occurrence Count", "Mothers Affected", "Prevalence %"]]
            for comp in cs:
                cs_table.append([
                    Paragraph(_fmt(comp.get('complication_type')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(comp.get('occurrence_count')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(comp.get('mothers_affected')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(comp.get('prevalence_pct')), TABLE_PARAGRAPH_STYLE),
                ])
            sections.append({"heading": "Complication Summary", "content": cs_table})
        
        # Medical Complications
        mc = data.get('medical_complications') or []
        if mc:
            mc_table = [["Mother Name", "Previous Illness", "Previous Hospitalization", "Pregnancy Complication", "Trimester"]]
            for med in mc:
                mc_table.append([
                    Paragraph(_fmt(med.get('mother_name')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(med.get('previous_illness')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(med.get('previous_hospitalization')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(med.get('previous_preg_complication')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(med.get('trimester_stage_name')), TABLE_PARAGRAPH_STYLE),
                ])
            sections.append({"heading": "Medical Complications", "content": mc_table})
        
        # Risk Referrals
        rr = data.get('risk_referrals') or []
        if rr:
            rr_table = [["Mother Name", "Risk Category", "Risk Count", "Trimester"]]
            for risk in rr:
                rr_table.append([
                    Paragraph(_fmt(risk.get('mother_name')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(risk.get('risk_category_name')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(risk.get('risk_count')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(risk.get('trimester_stage_name')), TABLE_PARAGRAPH_STYLE),
                ])
            sections.append({"heading": "Risk Referrals", "content": rr_table})
        
        header_lines_to_use = header_lines or self._default_header_lines()
        left_img_to_use = MaternalReportHelpers.resolve_image(left_image) if left_image else None
        right_img_to_use = MaternalReportHelpers.resolve_image(right_image) if right_image else None

        pdf_bytes = self._pdf.generate(
            title=f"Trimester {trimester} Complication & Referral Report - {year}",
            header_lines=header_lines_to_use,
            left_image_path=left_img_to_use,
            right_image_path=right_img_to_use,
            watermark_text=watermark,
            sections=sections,
        )

        return pdf_bytes, f"maternal_trimester_complication_{year}_T{trimester}.pdf"

    def generate_trimester_service_utilization_pdf(
        self,
        year: int,
        trimester: int,
        header_lines: Optional[list] = None,
        watermark: Optional[str] = None,
        left_image: Optional[str] = None,
        right_image: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate Trimester Service Utilization PDF."""
        if not self._reports_query:
            raise ValueError("MaternalReportsQuery not injected into service")
        
        data = self._reports_query.get_trimester_service_utilization(year, trimester)
        
        sections = []
        
        # Visit Counts
        vc = data.get('visit_counts') or {}
        vc_lines = [
            f"Total Mothers: {_fmt(vc.get('total_mothers'))}",
            f"Total Visits: {_fmt(vc.get('total_visits'))}",
            f"Avg Visits per Mother: {_fmt(vc.get('avg_visits_per_mother'))}",
        ]
        sections.append({"heading": "Visit Counts", "content": "<br/>".join(vc_lines)})
        
        # Lab Utilization
        lu = data.get('lab_utilization') or {}
        lu_lines = [
            f"Mothers with Labs: {_fmt(lu.get('mothers_with_labs'))}",
            f"Total Lab Tests: {_fmt(lu.get('total_lab_tests'))}",
            f"Lab Coverage: {_fmt(lu.get('lab_coverage_pct'))}%",
        ]
        sections.append({"heading": "Lab Utilization", "content": "<br/>".join(lu_lines)})
        
        # TT Vaccination Coverage
        ttvc = data.get('tt_vaccination_coverage') or {}
        ttvc_lines = [
            f"Mothers Vaccinated: {_fmt(ttvc.get('mothers_vaccinated'))}",
            f"Total Doses: {_fmt(ttvc.get('total_doses'))}",
            f"TT Coverage: {_fmt(ttvc.get('tt_coverage_pct'))}%",
        ]
        sections.append({"heading": "TT Vaccination Coverage", "content": "<br/>".join(ttvc_lines)})
        
        # Micronutrient Coverage
        mc = data.get('micronutrient_coverage') or {}
        mc_lines = [
            f"Mothers on Iron: {_fmt(mc.get('mothers_on_iron'))}",
            f"Mothers Dewormed: {_fmt(mc.get('mothers_dewormed'))}",
            f"Iron Coverage: {_fmt(mc.get('iron_coverage_pct'))}%",
        ]
        sections.append({"heading": "Micronutrient Coverage", "content": "<br/>".join(mc_lines)})
        
        # Service Completeness
        sc = data.get('service_completeness') or []
        if sc:
            sc_table = [["Mother Name", "Visits", "Lab", "TT", "Iron", "Services Completed"]]
            for mother in sc[:30]:
                sc_table.append([
                    Paragraph(_fmt(mother.get('mother_name')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('visits')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('has_lab')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('has_tt')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('has_iron')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('services_completed')), TABLE_PARAGRAPH_STYLE),
                ])
            sections.append({"heading": "Service Completeness (Top 30)", "content": sc_table})
        
        header_lines_to_use = header_lines or self._default_header_lines()
        left_img_to_use = MaternalReportHelpers.resolve_image(left_image) if left_image else None
        right_img_to_use = MaternalReportHelpers.resolve_image(right_image) if right_image else None

        pdf_bytes = self._pdf.generate(
            title=f"Trimester {trimester} Service Utilization Report - {year}",
            header_lines=header_lines_to_use,
            left_image_path=left_img_to_use,
            right_image_path=right_img_to_use,
            watermark_text=watermark,
            sections=sections,
        )

        return pdf_bytes, f"maternal_trimester_service_{year}_T{trimester}.pdf"

    def generate_annual_outcome_consolidated_pdf(
        self,
        year: int,
        header_lines: Optional[list] = None,
        watermark: Optional[str] = None,
        left_image: Optional[str] = None,
        right_image: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate Annual Maternal Outcome & Incident Consolidated PDF."""
        if not self._reports_query:
            raise ValueError("MaternalReportsQuery not injected into service")
        
        data = self._reports_query.get_annual_maternal_outcome_consolidated(year)
        
        sections = []
        
        # Pregnancy Outcomes
        po = data.get('pregnancy_outcomes') or {}
        po_lines = [
            f"Total Pregnancies: {_fmt(po.get('total_pregnancies'))}",
            f"Live Births: {_fmt(po.get('live_births'))}",
            f"Stillbirths: {_fmt(po.get('stillbirths'))}",
            f"Abortions: {_fmt(po.get('abortions'))}",
            f"Average Mother Age: {_fmt(po.get('avg_mother_age'))}",
            f"Teen Pregnancies: {_fmt(po.get('teen_pregnancies'))}",
            f"Underweight Mothers: {_fmt(po.get('underweight_mothers'))}",
        ]
        sections.append({"heading": "Pregnancy Outcomes", "content": "<br/>".join(po_lines)})
        
        # Delivery Type Breakdown
        dtb = data.get('delivery_type_breakdown') or []
        if dtb:
            dtb_table = [["Delivery Type", "Count", "Percentage"]]
            for delivery in dtb:
                dtb_table.append([
                    Paragraph(_fmt(delivery.get('delivery_type_name')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(delivery.get('delivery_count')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(delivery.get('percentage')), TABLE_PARAGRAPH_STYLE),
                ])
            sections.append({"heading": "Delivery Type Breakdown", "content": dtb_table})
        
        # Complications Summary
        cs = data.get('complications_summary') or []
        if cs:
            cs_table = [["Complication Type", "Mothers Affected", "Total Incidents"]]
            for comp in cs:
                cs_table.append([
                    Paragraph(_fmt(comp.get('complication_type')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(comp.get('mothers_affected')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(comp.get('total_incidents')), TABLE_PARAGRAPH_STYLE),
                ])
            sections.append({"heading": "Complications Summary", "content": cs_table})
        
        # Risk Distribution
        rd = data.get('risk_distribution') or []
        if rd:
            rd_table = [["Risk Category", "Mothers at Risk", "Risk Percentage"]]
            for risk in rd:
                rd_table.append([
                    Paragraph(_fmt(risk.get('risk_category_name')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(risk.get('mothers_at_risk')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(risk.get('risk_percentage')), TABLE_PARAGRAPH_STYLE),
                ])
            sections.append({"heading": "Risk Distribution", "content": rd_table})
        
        header_lines_to_use = header_lines or self._default_header_lines()
        left_img_to_use = MaternalReportHelpers.resolve_image(left_image) if left_image else None
        right_img_to_use = MaternalReportHelpers.resolve_image(right_image) if right_image else None

        pdf_bytes = self._pdf.generate(
            title=f"Annual Maternal Outcome Consolidated Report - {year}",
            header_lines=header_lines_to_use,
            left_image_path=left_img_to_use,
            right_image_path=right_img_to_use,
            watermark_text=watermark,
            sections=sections,
        )

        return pdf_bytes, f"maternal_annual_outcome_{year}.pdf"

    def generate_annual_coverage_scorecard_pdf(
        self,
        year: int,
        header_lines: Optional[list] = None,
        watermark: Optional[str] = None,
        left_image: Optional[str] = None,
        right_image: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate Annual Barangay Maternal Health Coverage Scorecard PDF."""
        if not self._reports_query:
            raise ValueError("MaternalReportsQuery not injected into service")
        
        data = self._reports_query.get_annual_coverage_scorecard(year)
        
        sections = []
        
        # Overall Scorecard
        os_data = data.get('overall_scorecard') or {}
        os_lines = [
            f"Total Mothers: {_fmt(os_data.get('total_mothers'))}",
            f"Mothers with 4+ Visits: {_fmt(os_data.get('mothers_4plus_visits'))} ({_fmt(os_data.get('prenatal_compliance_pct'))}%)",
            f"TT Compliant: {_fmt(os_data.get('mothers_tt_compliant'))} ({_fmt(os_data.get('tt_compliance_pct'))}%)",
            f"Mothers on Iron: {_fmt(os_data.get('mothers_on_iron'))} ({_fmt(os_data.get('iron_coverage_pct'))}%)",
            f"Mothers Dewormed: {_fmt(os_data.get('mothers_dewormed'))} ({_fmt(os_data.get('deworming_coverage_pct'))}%)",
        ]
        sections.append({"heading": "Overall Scorecard", "content": "<br/>".join(os_lines)})
        
        # Mother Scorecard
        ms = data.get('mother_scorecard') or []
        if ms:
            ms_table = [["Mother Name", "Total Visits", "4+ Visits", "TT Doses", "TT Met", "Iron", "Dewormed", "Score", "Level"]]
            for mother in ms[:30]:
                ms_table.append([
                    Paragraph(_fmt(mother.get('mother_name')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('total_visits')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('meets_4plus_visits')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('tt_doses')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('meets_tt_requirement')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('received_iron')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('received_deworming')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('compliance_score')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(mother.get('compliance_level')), TABLE_PARAGRAPH_STYLE),
                ])
            sections.append({"heading": "Mother Scorecard (Top 30)", "content": ms_table})
        
        header_lines_to_use = header_lines or self._default_header_lines()
        left_img_to_use = MaternalReportHelpers.resolve_image(left_image) if left_image else None
        right_img_to_use = MaternalReportHelpers.resolve_image(right_image) if right_image else None

        pdf_bytes = self._pdf.generate(
            title=f"Annual Coverage Scorecard - {year}",
            header_lines=header_lines_to_use,
            left_image_path=left_img_to_use,
            right_image_path=right_img_to_use,
            watermark_text=watermark,
            sections=sections,
        )

        return pdf_bytes, f"maternal_annual_coverage_{year}.pdf"

    def generate_annual_trend_analysis_pdf(
        self,
        year: int,
        header_lines: Optional[list] = None,
        watermark: Optional[str] = None,
        left_image: Optional[str] = None,
        right_image: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate Annual Trend Analysis & Forecasting PDF."""
        if not self._reports_query:
            raise ValueError("MaternalReportsQuery not injected into service")
        
        data = self._reports_query.get_annual_trend_analysis(year)
        
        sections = []
        
        # Monthly Aggregates
        ma = data.get('monthly_aggregates') or []
        if ma:
            ma_table = [["Month", "New Pregnancies", "Underweight Cases", "Teen Pregnancies"]]
            for month_data in ma:
                ma_table.append([
                    Paragraph(_fmt(month_data.get('month')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(month_data.get('new_pregnancies')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(month_data.get('underweight_cases')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(month_data.get('teen_pregnancies')), TABLE_PARAGRAPH_STYLE),
                ])
            sections.append({"heading": "Monthly Aggregates", "content": ma_table})
        
        # Risk Trends
        rt = data.get('risk_trends') or []
        if rt:
            rt_table = [["Month", "Mothers at Risk", "Obstetric Risks", "Medical Risks"]]
            for risk_trend in rt:
                rt_table.append([
                    Paragraph(_fmt(risk_trend.get('month')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(risk_trend.get('mothers_at_risk')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(risk_trend.get('obstetric_risks')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(risk_trend.get('medical_risks')), TABLE_PARAGRAPH_STYLE),
                ])
            sections.append({"heading": "Risk Trends", "content": rt_table})
        
        # Service Trends
        st = data.get('service_trends') or []
        if st:
            st_table = [["Month", "Total Visits", "TT Doses Given", "Lab Tests Conducted"]]
            for service_trend in st:
                st_table.append([
                    Paragraph(_fmt(service_trend.get('month')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(service_trend.get('total_visits')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(service_trend.get('tt_doses_given')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(service_trend.get('lab_tests_conducted')), TABLE_PARAGRAPH_STYLE),
                ])
            sections.append({"heading": "Service Trends", "content": st_table})
        
        # Yearly Summary
        ys = data.get('yearly_summary') or {}
        ys_lines = [
            f"Total Pregnancies: {_fmt(ys.get('total_pregnancies_year'))}",
            f"Avg per Month: {_fmt(ys.get('avg_pregnancies_per_month'))}",
            f"Peak Month: {_fmt(ys.get('peak_month_pregnancies'))} pregnancies",
            f"Lowest Month: {_fmt(ys.get('lowest_month_pregnancies'))} pregnancies",
        ]
        sections.append({"heading": "Yearly Summary", "content": "<br/>".join(ys_lines)})
        
        # Forecast Projection
        fp = data.get('forecast_projection') or {}
        fp_lines = [
            f"Forecast Type: {_fmt(fp.get('forecast_type'))}",
            f"Projected Pregnancies: {_fmt(fp.get('projected_pregnancies'))}",
            f"Estimated High Risk Cases: {_fmt(fp.get('estimated_high_risk_cases'))}",
            f"Estimated Total Visits: {_fmt(fp.get('estimated_total_visits'))}",
        ]
        sections.append({"heading": "Next Year Forecast", "content": "<br/>".join(fp_lines)})
        
        header_lines_to_use = header_lines or self._default_header_lines()
        left_img_to_use = MaternalReportHelpers.resolve_image(left_image) if left_image else None
        right_img_to_use = MaternalReportHelpers.resolve_image(right_image) if right_image else None

        pdf_bytes = self._pdf.generate(
            title=f"Annual Trend Analysis & Forecasting - {year}",
            header_lines=header_lines_to_use,
            left_image_path=left_img_to_use,
            right_image_path=right_img_to_use,
            watermark_text=watermark,
            sections=sections,
        )

        return pdf_bytes, f"maternal_annual_trend_{year}.pdf"

    def generate_all_analytics_reports_pdf(
        self,
        year: int,
        month: int,
        header_lines: Optional[list] = None,
        watermark: Optional[str] = None,
        left_image: Optional[str] = None,
        right_image: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate consolidated PDF with all analytics reports (excludes maternal summary)."""
        if not self._reports_query:
            raise ValueError("MaternalReportsQuery not injected into service")
        
        all_sections = []
        
        # Monthly Reports
        monthly_data_1 = self._reports_query.get_monthly_visit_compliance(year, month)
        vs = monthly_data_1.get('visit_summary') or {}
        vs_lines = [
            f"Total Scheduled: {_fmt(vs.get('total_scheduled'))}",
            f"Completed: {_fmt(vs.get('completed_visits'))}",
            f"Missed: {_fmt(vs.get('missed_visits'))}",
            f"Compliance Rate: {_fmt(vs.get('compliance_rate'))}%",
        ]
        all_sections.append({"heading": "1. Monthly Visit Compliance", "content": "<br/>".join(vs_lines)})
        
        monthly_data_2 = self._reports_query.get_monthly_risk_indicator_summary(year, month)
        rs = monthly_data_2.get('risk_summary') or {}
        rs_lines = [
            f"Total Mothers: {_fmt(rs.get('total_mothers'))}",
            f"Underweight: {_fmt(rs.get('underweight_count'))} ({_fmt(rs.get('underweight_pct'))}%)",
            f"Teen Pregnancy: {_fmt(rs.get('teen_pregnancy_count'))}",
            f"Hypertension: {_fmt(rs.get('hypertension_count'))}",
        ]
        all_sections.append({"heading": "2. Monthly Risk Indicators", "content": "<br/>".join(rs_lines)})
        
        monthly_data_3 = self._reports_query.get_monthly_immunization_supplement_adherence(year, month)
        ms = monthly_data_3.get('micronutrient_summary') or {}
        ms_lines = [
            f"Iron Started: {_fmt(ms.get('iron_started'))}",
            f"Iron Completed: {_fmt(ms.get('iron_completed'))}",
            f"Iron Completion Rate: {_fmt(ms.get('iron_completion_rate'))}%",
        ]
        all_sections.append({"heading": "3. Monthly Immunization & Supplements", "content": "<br/>".join(ms_lines)})
        
        # Trimester Reports (all 3 trimesters)
        for tri in [1, 2, 3]:
            tri_data_1 = self._reports_query.get_trimester_health_outcome_trajectory(year, tri)
            mt_list = tri_data_1.get('mother_trajectory') or []
            if mt_list:
                mt_summary = f"Tracking {len(mt_list)} mothers in trimester {tri}"
            else:
                mt_summary = "No data available"
            all_sections.append({"heading": f"4.{tri} Trimester {tri} Health Outcomes", "content": mt_summary})
        
        # Annual Reports
        annual_data_1 = self._reports_query.get_annual_maternal_outcome_consolidated(year)
        po = annual_data_1.get('pregnancy_outcomes') or {}
        po_lines = [
            f"Total Pregnancies: {_fmt(po.get('total_pregnancies'))}",
            f"Live Births: {_fmt(po.get('live_births'))}",
            f"Teen Pregnancies: {_fmt(po.get('teen_pregnancies'))}",
        ]
        all_sections.append({"heading": "7. Annual Outcome Consolidated", "content": "<br/>".join(po_lines)})
        
        annual_data_2 = self._reports_query.get_annual_coverage_scorecard(year)
        os_data = annual_data_2.get('overall_scorecard') or {}
        os_lines = [
            f"Total Mothers: {_fmt(os_data.get('total_mothers'))}",
            f"Prenatal Compliance: {_fmt(os_data.get('prenatal_compliance_pct'))}%",
            f"TT Compliance: {_fmt(os_data.get('tt_compliance_pct'))}%",
        ]
        all_sections.append({"heading": "8. Annual Coverage Scorecard", "content": "<br/>".join(os_lines)})
        
        annual_data_3 = self._reports_query.get_annual_trend_analysis(year)
        ys = annual_data_3.get('yearly_summary') or {}
        fp = annual_data_3.get('forecast_projection') or {}
        trend_lines = [
            f"Total Pregnancies {year}: {_fmt(ys.get('total_pregnancies_year'))}",
            f"Projected Next Year: {_fmt(fp.get('projected_pregnancies'))}",
        ]
        all_sections.append({"heading": "9. Annual Trend Analysis", "content": "<br/>".join(trend_lines)})
        
        header_lines_to_use = header_lines or self._default_header_lines()
        left_img_to_use = MaternalReportHelpers.resolve_image(left_image) if left_image else None
        right_img_to_use = MaternalReportHelpers.resolve_image(right_image) if right_image else None

        pdf_bytes = self._pdf.generate(
            title=f"Maternal Health Analytics - All Reports {year}/{month:02d}",
            header_lines=header_lines_to_use,
            left_image_path=left_img_to_use,
            right_image_path=right_img_to_use,
            watermark_text=watermark,
            sections=all_sections,
        )

        return pdf_bytes, f"maternal_all_analytics_{year}_{month:02d}.pdf"
