from typing import Optional, Tuple, List, Dict, Any

from src.infra.utilities.pdf_generator import PdfGenerator
from src.infra.utilities.age_calculator import AgeCalculator
from src.infra.repositories.child_report_repository import ChildReportRepository
from src.infra.repositories.queries.child_reports_query import ChildReportsQuery
from src.infra.exceptions.generic_child_health_record_exceptions import GenericChildHealthRecordException
import logging
from src.app.utility.maternal_report_helpers import MaternalReportHelpers
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER

# Paragraph style for table cells to ensure wrapping, prevent overflow,
# and center the cell contents
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

logger = logging.getLogger(__name__)


class ChildReportService:
    """Service to generate child health summary reports.

    This mirrors the maternal report service in structure and PDF settings
    so reports are consistent across modules.
    """

    def __init__(self, repository: ChildReportRepository, reports_query: Optional[ChildReportsQuery] = None, pdf_generator: Optional[PdfGenerator] = None):
        self._repo = repository
        self._reports_query = reports_query
        self._pdf = pdf_generator or PdfGenerator()

    def generate_child_summary_pdf(
        self,
        child_record_id: int,
        header_lines: Optional[list] = None,
        watermark: Optional[str] = None,
        left_image: Optional[str] = None,
        right_image: Optional[str] = None,
        generated_by_name: Optional[str] = None,
        generated_by_role: Optional[str] = None,
    ) -> Tuple[bytes, List[str], str]:
        try:
            payload = self._repo.assemble_report_payload(child_record_id)

            # Track missing fields so callers (API) can surface a warning
            missing_fields: List[str] = []

            if not payload.get("patient_info"):
                logger.error("Child health record %s not found", child_record_id)
                raise GenericChildHealthRecordException("Child health record not found")

            # Quick presence checks for many required fields from the
            # user's checklist. We collect human-readable labels for any
            # missing items and return them to the API which will expose
            # them via a response header.
            hi = payload.get("health_record_info") or {}
            sp = payload.get("screening_package") or {}
            ml = payload.get("monitoring_logs") or []
            imm_mat = payload.get("immunization_matrix") or []
            nb = payload.get("newborn_screening") or {}
            bf_by_person = payload.get("feeding_checks_by_person") or []
            basic_person = payload.get("basic_by_person") or {}

            # Identification block
            if not (hi.get("child_full_name") or payload["patient_info"].get("first_name")):
                missing_fields.append("child full name")
            if not (hi.get("date_of_birth") or payload["patient_info"].get("birthdate")):
                missing_fields.append("birthdate")
            if not (hi.get("child_gender") or payload["patient_info"].get("sex")):
                missing_fields.append("sex/gender")
            if not (hi.get("family_num") or payload["patient_info"].get("family_num")):
                missing_fields.append("family number")
            if not (hi.get("ufc_num") or basic_person.get("ufc_num") or payload["patient_info"].get("family_num")):
                missing_fields.append("ufc number")

            # Place of delivery
            if not (hi.get("place_of_delivery") or payload["patient_info"].get("delivery_place_type_name")):
                missing_fields.append("place of delivery")

            # Parents data
            if not (hi.get("mother_full_name") or payload["patient_info"].get("mother_first_name")):
                missing_fields.append("mother name")
            if not (hi.get("mothers_age") and hi.get("mothers_occupation") or basic_person.get("MOTHER_OCCUPATION")):
                # we check occupation/age but tolerate partials
                missing_fields.append("mother age/occupation")
            if not (hi.get("father_full_name") or payload["patient_info"].get("father_first_name")):
                missing_fields.append("father name")
            if not (hi.get("fathers_age") and hi.get("fathers_occupation") or basic_person.get("FATHER_OCCUPATION")):
                missing_fields.append("father age/occupation")

            # Address
            if not (hi.get("child_complete_address") or basic_person.get("ADDRESS")):
                missing_fields.append("complete address")

            # Newborn screening / feeding type
            if not (nb and (nb.get("feeding_type_name") or nb.get("referred_nbs_date"))):
                missing_fields.append("newborn screening (feeding type / referred date)")

            # Breastfeeding checks (we expect up to the last 5 checks)
            if not bf_by_person:
                # fallback to breastfeeding_checks already in payload
                if not payload.get("breastfeeding_checks"):
                    missing_fields.append("breastfeeding checks")

            # Immunizations
            if not imm_mat and not payload.get("all_immunizations"):
                missing_fields.append("immunizations")

            # Screening details (birth weight, anemia, iron seen/given for 2-6 mos)
            if not (sp and (sp.get("birth_weight") is not None)):
                missing_fields.append("birth weight")
            if not (sp and (sp.get("anemic_2_59_seen_date") or sp.get("anemic_2_59_given_iron_date"))):
                missing_fields.append("anemia screening/iron given details")
            if not (sp and (sp.get("seen_2_6_mos_date") or sp.get("given_2_6_mos_date"))):
                missing_fields.append("iron (2-6 months) seen/given dates")

            # Iron supplementation dates
            if not (sp and (sp.get("iron_date_started") or sp.get("iron_date_completed") or payload.get("iron_supplements"))):
                missing_fields.append("iron supplementation dates")

            # Vitamin A stages
            if not (sp and (sp.get("vit_a_given_1") or sp.get("vit_a_given_2") or sp.get("vit_a_given_3") or payload.get("vitamin_a"))):
                missing_fields.append("vitamin A dates (stages 1-3)")

            # Visits / monitoring logs with measurements
            if not ml:
                missing_fields.append("visit monitoring logs (weight/temp/height/findings/notes)")

            sections = []

            # Patient Info
            p = payload.get("patient_info") or {}
            patient_lines = [
                f"Name: {_fmt(p.get('first_name'))} {_fmt(p.get('middle_name'))} {_fmt(p.get('last_name'))}",
                f"Age: {_fmt(AgeCalculator.get_readable_age_from_payload(p))}",
                f"Birthdate: {_fmt(p.get('birthdate'))}",
                f"Birth order: {_fmt(p.get('birth_order'))}",
                f"Delivery place: {_fmt(p.get('delivery_place_type_name'))}",
                f"Mother: {_fmt(p.get('mother_first_name'))} {_fmt(p.get('mother_last_name'))}",
                f"Father: {_fmt(p.get('father_first_name'))} {_fmt(p.get('father_last_name'))}",
                f"Family #: {_fmt(p.get('family_num'))}",
            ]
            sections.append({"heading": "Patient Information", "content": "<br/>".join(patient_lines)})

            # Visit summary
            visits = payload.get("visits") or []
            last_visit = visits[0] if visits else None
            visit_lines = [f"Total visits: {len(visits)}"]
            if last_visit:
                visit_lines.append(f"Last visit: {last_visit.get('visit_date','')}")
            sections.append({"heading": "Visit Summary", "content": "<br/>".join(visit_lines)})

            # Immunizations
            imms = payload.get("immunizations") or []
            imm_table = [["Vaccine", "Stage", "Date Given"]]
            for im in imms:
                imm_table.append([
                    im.get("immunization_type_name", ""),
                    im.get("immunization_stage_name", ""),
                    im.get("date_given", ""),
                ])
            # wrap table cells in Paragraphs so long text will wrap inside table cells
            imm_table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in imm_table]
            sections.append({"heading": "Immunizations", "content": imm_table_wrapped})

            # Vitamin A
            vits = payload.get("vitamin_a") or []
            vit_table = [["Date Given", "Stage", "Visit ID"]]
            for v in vits:
                vit_table.append([v.get('date_given',''), v.get('vit_stage_id',''), v.get('visit_id','')])
            vit_table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in vit_table]
            sections.append({"heading": "Vitamin A Given", "content": vit_table_wrapped})

            # Iron supplements
            irons = payload.get("iron_supplements") or []
            iron_lines = []
            for i in irons:
                iron_lines.append(f"Started: {_fmt(i.get('date_started'))} | Completed: {_fmt(i.get('date_completed'))}")
            sections.append({"heading": "Iron Supplements", "content": "<br/>".join(iron_lines)})

            # Screening assessments
            screens = payload.get("screenings") or []
            if screens:
                screen_table = [["Date", "Birth Weight", "Low Birth Weight", "Anemic Given Iron Date"]]
                for s in screens:
                    screen_table.append([
                        s.get("date_assessed", ""),
                        s.get("birth_weight", ""),
                        MaternalReportHelpers.bool_to_yesno(s.get("is_low_birth_weight", None)),
                        s.get("anemic_given_iron_date", ""),
                    ])
                screen_table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in screen_table]
                sections.append({"heading": "Screening Assessments", "content": screen_table_wrapped})

            # Breastfeeding checks & feeding types
            bf = payload.get("breastfeeding_checks") or []
            feeding = payload.get("feeding_types") or []
            bf_lines = [f"Check Date: {b.get('check_date','')}" for b in bf]
            if feeding:
                feed_table = [["Feeding Type", "Visit ID", "Referred Screening Date"]]
                for f in feeding:
                    feed_table.append([
                        f.get("feeding_type_name", ""),
                        f.get("visit_id", ""),
                        f.get("referred_newborn_screening_date", ""),
                    ])
                feed_table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in feed_table]
                sections.append({"heading": "Feeding Types", "content": feed_table_wrapped})
            if bf_lines:
                sections.append({"heading": "Breastfeeding Checks", "content": "<br/>".join(bf_lines)})

            # Visit schedules
            schedules = payload.get("visit_schedules") or []
            if schedules:
                sched_table = [["Scheduled Date", "Scheduled Time", "Status", "Purpose"]]
                for s in schedules:
                    sched_table.append([
                        s.get("scheduled_date", ""),
                        s.get("scheduled_time", ""),
                        s.get("status_id", ""),
                        s.get("visit_purpose", "") or "",
                    ])
                sched_table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in sched_table]
                sections.append({"heading": "Visit Schedules", "content": sched_table_wrapped})

            # Prepare document metadata & defaults (reuse maternal defaults)
            name = p.get('first_name','')
            last = p.get('last_name','')
            title = f"Child Health Summary Report - {name} {last}".strip()

            default_header_lines = [
                ("Republic of the Philippines", 14),
                ("Barangay Health Center", 14),
                ("BARANGAY SEÑOR SANTO NIÑO", 14),
                ("032 Legaspi Street, Cebu City", 11),
            ]

            header_lines_to_use = header_lines or default_header_lines
            watermark_to_use = watermark or "CONFIDENTIAL HEALTH INFORMATION"

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

            fname = f"{_sanitize(last)}_{_sanitize(first)}_{child_record_id}.pdf"

            return pdf_bytes, missing_fields, fname
        except Exception:
            logger.exception("Failed to generate child summary PDF for child record %s", child_record_id)
            raise

    def generate_monthly_immunization_coverage_pdf(
        self,
        year: int,
        month: int,
        header_lines: Optional[list] = None,
        watermark: Optional[str] = None,
        left_image: Optional[str] = None,
        right_image: Optional[str] = None,
        generated_by_name: Optional[str] = None,
        generated_by_role: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate Monthly Immunization Coverage & Compliance Report PDF."""
        try:
            if not self._reports_query:
                raise ValueError("ChildReportsQuery not injected into service")

            data = self._reports_query.get_monthly_immunization_coverage(year, month)
            sections = []

            # Coverage Summary
            coverage = data.get('coverage_summary') or {}
            if coverage:
                summary_lines = [
                    f"Total Children: {_fmt(coverage.get('total_children'))}",
                    f"Children Vaccinated: {_fmt(coverage.get('children_vaccinated'))}",
                    f"Coverage Percentage: {_fmt(coverage.get('coverage_percentage'))}%",
                ]
                sections.append({"heading": "Coverage Summary", "content": "<br/>".join(summary_lines)})

            # Type Coverage
            type_cov = data.get('type_coverage') or []
            if type_cov:
                table = [["Vaccine Type", "Doses Given", "Children Receiving"]]
                for tc in type_cov:
                    table.append([tc.get('vaccine_type',''), str(tc.get('doses_given',0)), str(tc.get('children_receiving',0))])
                table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                sections.append({"heading": "Immunization Type Coverage", "content": table_wrapped})

            # Repeat Offenders
            repeat_off = data.get('repeat_offenders') or []
            if repeat_off:
                table = [["Child Name", "Missed Visits", "Missing Vaccines"]]
                for ro in repeat_off:
                    table.append([ro.get('child_name',''), str(ro.get('missed_visits',0)), ro.get('missing_vaccines','')])
                table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                sections.append({"heading": "Children Falling Behind Schedule", "content": table_wrapped})

            title = f"Monthly Immunization Coverage Report - {year}/{month:02d}"
            header_lines_to_use = header_lines or self._default_header_lines()
            watermark_to_use = watermark or "CONFIDENTIAL HEALTH INFORMATION"
            left_img = MaternalReportHelpers.resolve_image(left_image) if left_image else None
            right_img = MaternalReportHelpers.resolve_image(right_image) if right_image else None

            pdf_bytes = self._pdf.generate(
                title=title,
                header_lines=header_lines_to_use,
                header_color="#002060",
                left_image_path=left_img,
                right_image_path=right_img,
                watermark_text=watermark_to_use,
                sections=sections,
                additional_signatory_name=generated_by_name,
                additional_signatory_role=generated_by_role,
            )

            filename = f"immunization_coverage_{year}_{month:02d}.pdf"
            return pdf_bytes, filename
        except Exception:
            logger.exception("Failed to generate monthly immunization coverage PDF for %s/%s", year, month)
            raise

    def generate_monthly_visit_completion_pdf(
        self,
        year: int,
        month: int,
        header_lines: Optional[list] = None,
        watermark: Optional[str] = None,
        left_image: Optional[str] = None,
        right_image: Optional[str] = None,
        generated_by_name: Optional[str] = None,
        generated_by_role: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate Monthly Visit Completion & Missed Visit Report PDF."""
        try:
            if not self._reports_query:
                raise ValueError("ChildReportsQuery not injected into service")

            data = self._reports_query.get_monthly_visit_completion(year, month)
            sections = []

            # Visit Summary
            summary = data.get('visit_summary') or {}
            if summary:
                summary_lines = [
                    f"Total Scheduled: {_fmt(summary.get('total_scheduled'))}",
                    f"Completed Visits: {_fmt(summary.get('completed_visits'))}",
                    f"Missed Visits: {_fmt(summary.get('missed_visits'))}",
                    f"Delayed Visits: {_fmt(summary.get('delayed_visits'))}",
                    f"Average Delay: {_fmt(summary.get('avg_delay_days'))} days",
                    f"Completion Rate: {_fmt(summary.get('completion_rate'))}%",
                ]
                sections.append({"heading": "Visit Summary", "content": "<br/>".join(summary_lines)})

            # Household Performance
            household = data.get('household_performance') or []
            if household:
                table = [["Family ID", "Total Visits", "Missed Count", "Miss Rate %"]]
                for h in household:
                    table.append([str(h.get('family_id','')), str(h.get('total_visits',0)), str(h.get('missed_count',0)), str(h.get('miss_rate',0))])
                table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                sections.append({"heading": "Households with Repeated Missed Visits", "content": table_wrapped})

            # Worker Performance
            worker = data.get('worker_performance') or []
            if worker:
                table = [["Worker Name", "Visits Handled", "Completed", "Completion Rate %"]]
                for w in worker:
                    table.append([w.get('worker_name',''), str(w.get('visits_handled',0)), str(w.get('completed',0)), str(w.get('completion_rate',0))])
                table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                sections.append({"heading": "Worker Performance", "content": table_wrapped})

            title = f"Monthly Visit Completion Report - {year}/{month:02d}"
            header_lines_to_use = header_lines or self._default_header_lines()
            watermark_to_use = watermark or "CONFIDENTIAL HEALTH INFORMATION"
            left_img = MaternalReportHelpers.resolve_image(left_image) if left_image else None
            right_img = MaternalReportHelpers.resolve_image(right_image) if right_image else None

            pdf_bytes = self._pdf.generate(
                title=title,
                header_lines=header_lines_to_use,
                header_color="#002060",
                left_image_path=left_img,
                right_image_path=right_img,
                watermark_text=watermark_to_use,
                sections=sections,
                additional_signatory_name=generated_by_name,
                additional_signatory_role=generated_by_role,
            )

            filename = f"visit_completion_{year}_{month:02d}.pdf"
            return pdf_bytes, filename
        except Exception:
            logger.exception("Failed to generate monthly visit completion PDF for %s/%s", year, month)
            raise

    def generate_monthly_growth_nutrition_pdf(
        self,
        year: int,
        month: int,
        header_lines: Optional[list] = None,
        watermark: Optional[str] = None,
        left_image: Optional[str] = None,
        right_image: Optional[str] = None,
        generated_by_name: Optional[str] = None,
        generated_by_role: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate Monthly Growth & Nutrition Monitoring Report PDF."""
        try:
            if not self._reports_query:
                raise ValueError("ChildReportsQuery not injected into service")

            data = self._reports_query.get_monthly_growth_nutrition(year, month)
            sections = []

            # Nutrition Summary
            summary = data.get('nutrition_summary') or {}
            if summary:
                summary_lines = [
                    f"Total Monitored: {_fmt(summary.get('total_monitored'))}",
                    f"Underweight Cases: {_fmt(summary.get('underweight_count'))}",
                    f"Stunted Cases: {_fmt(summary.get('stunted_count'))}",
                    f"Fever Cases: {_fmt(summary.get('fever_cases'))}",
                    f"Average Weight: {_fmt(summary.get('avg_weight'))} kg",
                    f"Average Height: {_fmt(summary.get('avg_height'))} cm",
                    f"Average Temperature: {_fmt(summary.get('avg_temperature'))} °C",
                ]
                sections.append({"heading": "Nutrition Summary", "content": "<br/>".join(summary_lines)})

            # Growth Consistency
            growth = data.get('growth_consistency') or []
            if growth:
                table = [["Child Name", "Check Count", "Weight Variance", "Height Variance", "Growth Pattern"]]
                for g in growth:
                    table.append([g.get('child_name',''), str(g.get('check_count',0)), str(g.get('weight_variance',0)), str(g.get('height_variance',0)), g.get('growth_pattern','')])
                table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                sections.append({"heading": "Growth Consistency Analysis", "content": table_wrapped})

            # Hotspot Analysis
            hotspot = data.get('hotspot_analysis') or []
            if hotspot:
                table = [["Purok", "Children Monitored", "Underweight", "Stunted", "Malnutrition Rate %"]]
                for h in hotspot:
                    table.append([h.get('purok',''), str(h.get('children_monitored',0)), str(h.get('underweight_cases',0)), str(h.get('stunted_cases',0)), str(h.get('malnutrition_rate',0))])
                table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                sections.append({"heading": "Geographic Hotspots (Purok)", "content": table_wrapped})

            title = f"Monthly Growth & Nutrition Report - {year}/{month:02d}"
            header_lines_to_use = header_lines or self._default_header_lines()
            watermark_to_use = watermark or "CONFIDENTIAL HEALTH INFORMATION"
            left_img = MaternalReportHelpers.resolve_image(left_image) if left_image else None
            right_img = MaternalReportHelpers.resolve_image(right_image) if right_image else None

            pdf_bytes = self._pdf.generate(
                title=title,
                header_lines=header_lines_to_use,
                header_color="#002060",
                left_image_path=left_img,
                right_image_path=right_img,
                watermark_text=watermark_to_use,
                sections=sections,
                additional_signatory_name=generated_by_name,
                additional_signatory_role=generated_by_role,
            )

            filename = f"growth_nutrition_{year}_{month:02d}.pdf"
            return pdf_bytes, filename
        except Exception:
            logger.exception("Failed to generate monthly growth nutrition PDF for %s/%s", year, month)
            raise

    def generate_annual_screening_risk_pdf(
        self,
        year: int,
        header_lines: Optional[list] = None,
        watermark: Optional[str] = None,
        left_image: Optional[str] = None,
        right_image: Optional[str] = None,
        generated_by_name: Optional[str] = None,
        generated_by_role: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate Annual Screening & Risk Factor Summary PDF."""
        try:
            if not self._reports_query:
                raise ValueError("ChildReportsQuery not injected into service")

            data = self._reports_query.get_annual_screening_risk(year)
            sections = []

            # Risk Summary
            summary = data.get('risk_summary') or {}
            if summary:
                summary_lines = [
                    f"Total Screenings: {_fmt(summary.get('total_screenings'))}",
                    f"Low Birth Weight Cases: {_fmt(summary.get('low_birth_weight_cases'))}",
                    f"Anemia Screenings: {_fmt(summary.get('anemia_screenings'))}",
                    f"Anemia Supplemented: {_fmt(summary.get('anemia_supplemented'))}",
                    f"Iron Screenings (2-6mo): {_fmt(summary.get('iron_screenings_2_6mo'))}",
                    f"Iron Supplemented (2-6mo): {_fmt(summary.get('iron_supplemented_2_6mo'))}",
                    f"Average Birth Weight: {_fmt(summary.get('avg_birth_weight'))} kg",
                    f"LBW Rate: {_fmt(summary.get('lbw_rate'))}%",
                ]
                sections.append({"heading": "Annual Risk Summary", "content": "<br/>".join(summary_lines)})

            # Monthly Trends
            trends = data.get('monthly_trends') or []
            if trends:
                table = [["Month", "Screenings", "LBW Cases", "Anemia Cases", "LBW Rate %"]]
                for t in trends:
                    table.append([str(t.get('month','')), str(t.get('screenings_count',0)), str(t.get('lbw_cases',0)), str(t.get('anemia_cases',0)), str(t.get('lbw_rate_pct',0))])
                table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                sections.append({"heading": "Month-to-Month Risk Trends", "content": table_wrapped})

            # Early Risk Populations
            early_risk = data.get('early_risk_populations') or []
            if early_risk:
                table = [["Child Name", "Birth Weight", "LBW", "Anemia Status", "Purok"]]
                for er in early_risk:
                    table.append([er.get('child_name',''), str(er.get('birth_weight','')), str(er.get('is_low_birth_weight','')), er.get('anemia_status',''), er.get('purok','')])
                table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                sections.append({"heading": "High-Risk Children", "content": table_wrapped})

            title = f"Annual Screening & Risk Factor Report - {year}"
            header_lines_to_use = header_lines or self._default_header_lines()
            watermark_to_use = watermark or "CONFIDENTIAL HEALTH INFORMATION"
            left_img = MaternalReportHelpers.resolve_image(left_image) if left_image else None
            right_img = MaternalReportHelpers.resolve_image(right_image) if right_image else None

            pdf_bytes = self._pdf.generate(
                title=title,
                header_lines=header_lines_to_use,
                header_color="#002060",
                left_image_path=left_img,
                right_image_path=right_img,
                watermark_text=watermark_to_use,
                sections=sections,
                additional_signatory_name=generated_by_name,
                additional_signatory_role=generated_by_role,
            )

            filename = f"screening_risk_{year}.pdf"
            return pdf_bytes, filename
        except Exception:
            logger.exception("Failed to generate annual screening risk PDF for %s", year)
            raise

    def generate_annual_immunization_performance_pdf(
        self,
        year: int,
        header_lines: Optional[list] = None,
        watermark: Optional[str] = None,
        left_image: Optional[str] = None,
        right_image: Optional[str] = None,
        generated_by_name: Optional[str] = None,
        generated_by_role: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate Annual Immunization Performance Dashboard PDF."""
        try:
            if not self._reports_query:
                raise ValueError("ChildReportsQuery not injected into service")

            data = self._reports_query.get_annual_immunization_performance(year)
            sections = []

            # Vaccine Coverage
            coverage = data.get('vaccine_coverage') or []
            if coverage:
                table = [["Vaccine", "Doses Administered", "Children Immunized", "Coverage Rate %"]]
                for c in coverage:
                    table.append([c.get('vaccine_name',''), str(c.get('doses_administered',0)), str(c.get('children_immunized',0)), str(c.get('coverage_rate',0))])
                table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                sections.append({"heading": "Full-Year Vaccine Coverage", "content": table_wrapped})

            # Seasonal Trends
            seasonal = data.get('seasonal_trends') or []
            if seasonal:
                table = [["Month", "Total Doses", "Children Immunized", "Vaccine Types"]]
                for s in seasonal:
                    table.append([str(s.get('month','')), str(s.get('total_doses',0)), str(s.get('children_immunized',0)), s.get('vaccine_types','')])
                table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                sections.append({"heading": "Seasonal Immunization Trends", "content": table_wrapped})

            # Year-over-Year Comparison
            yoy = data.get('yoy_comparison') or []
            if yoy:
                table = [["Year", "Total Immunizations", "Children Immunized", "Vaccine Types Used"]]
                for y in yoy:
                    table.append([str(y.get('year','')), str(y.get('total_immunizations',0)), str(y.get('children_immunized',0)), str(y.get('vaccine_types_used',0))])
                table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                sections.append({"heading": "Year-over-Year Comparison", "content": table_wrapped})

            # Herd Immunity
            herd = data.get('herd_immunity') or []
            if herd:
                table = [["Vaccine Type", "Immunized Children", "Total Children", "Coverage %", "Status"]]
                for h in herd:
                    table.append([h.get('vaccine_type',''), str(h.get('immunized_children',0)), str(h.get('total_children',0)), str(h.get('coverage_percentage',0)), h.get('herd_immunity_status','')])
                table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                sections.append({"heading": "Herd Immunity Indicators", "content": table_wrapped})

            title = f"Annual Immunization Performance Report - {year}"
            header_lines_to_use = header_lines or self._default_header_lines()
            watermark_to_use = watermark or "CONFIDENTIAL HEALTH INFORMATION"
            left_img = MaternalReportHelpers.resolve_image(left_image) if left_image else None
            right_img = MaternalReportHelpers.resolve_image(right_image) if right_image else None

            pdf_bytes = self._pdf.generate(
                title=title,
                header_lines=header_lines_to_use,
                header_color="#002060",
                left_image_path=left_img,
                right_image_path=right_img,
                watermark_text=watermark_to_use,
                sections=sections,
                additional_signatory_name=generated_by_name,
                additional_signatory_role=generated_by_role,
            )

            filename = f"immunization_performance_{year}.pdf"
            return pdf_bytes, filename
        except Exception:
            logger.exception("Failed to generate annual immunization performance PDF for %s", year)
            raise

    def generate_annual_growth_development_pdf(
        self,
        year: int,
        header_lines: Optional[list] = None,
        watermark: Optional[str] = None,
        left_image: Optional[str] = None,
        right_image: Optional[str] = None,
        generated_by_name: Optional[str] = None,
        generated_by_role: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate Annual Growth & Development Trend Report PDF."""
        try:
            if not self._reports_query:
                raise ValueError("ChildReportsQuery not injected into service")

            data = self._reports_query.get_annual_growth_development(year)
            sections = []

            # Growth by Age Group
            age_groups = data.get('growth_by_age_group') or []
            if age_groups:
                table = [["Age Group", "Children", "Avg Weight", "Avg Height", "Weight Range", "Height Range"]]
                for ag in age_groups:
                    weight_range = f"{ag.get('min_weight','')} - {ag.get('max_weight','')} kg"
                    height_range = f"{ag.get('min_height','')} - {ag.get('max_height','')} cm"
                    table.append([ag.get('age_group',''), str(ag.get('children_count',0)), str(ag.get('avg_weight',0)), str(ag.get('avg_height',0)), weight_range, height_range])
                table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                sections.append({"heading": "Growth by Age Group", "content": table_wrapped})

            # Chronic Malnutrition
            chronic = data.get('chronic_malnutrition') or []
            if chronic:
                table = [["Child Name", "Check Count", "Avg Weight", "Avg Height", "Underweight Checks", "Purok"]]
                for c in chronic:
                    table.append([c.get('child_name',''), str(c.get('check_count',0)), str(c.get('avg_weight',0)), str(c.get('avg_height',0)), str(c.get('underweight_checks',0)), c.get('purok','')])
                table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                sections.append({"heading": "Chronic Malnutrition Cases", "content": table_wrapped})

            # Purok Disparities
            purok = data.get('purok_disparities') or []
            if purok:
                table = [["Purok", "Children", "Avg Weight", "Avg Height", "Malnutrition Cases", "Malnutrition Rate %"]]
                for p in purok:
                    table.append([p.get('purok',''), str(p.get('children_count',0)), str(p.get('avg_weight',0)), str(p.get('avg_height',0)), str(p.get('malnutrition_cases',0)), str(p.get('malnutrition_rate',0))])
                table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                sections.append({"heading": "Purok-Level Disparities", "content": table_wrapped})

            # Program Correlation
            program = data.get('program_correlation') or []
            if program:
                table = [["Program", "Value", "Children", "Avg Weight", "Avg Height"]]
                for pr in program:
                    table.append([pr.get('program_name',''), pr.get('program_value',''), str(pr.get('children_count',0)), str(pr.get('avg_weight',0)), str(pr.get('avg_height',0))])
                table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                sections.append({"heading": "Program Correlation Analysis", "content": table_wrapped})

            title = f"Annual Growth & Development Report - {year}"
            header_lines_to_use = header_lines or self._default_header_lines()
            watermark_to_use = watermark or "CONFIDENTIAL HEALTH INFORMATION"
            left_img = MaternalReportHelpers.resolve_image(left_image) if left_image else None
            right_img = MaternalReportHelpers.resolve_image(right_image) if right_image else None

            pdf_bytes = self._pdf.generate(
                title=title,
                header_lines=header_lines_to_use,
                header_color="#002060",
                left_image_path=left_img,
                right_image_path=right_img,
                watermark_text=watermark_to_use,
                sections=sections,
                additional_signatory_name=generated_by_name,
                additional_signatory_role=generated_by_role,
            )

            filename = f"growth_development_{year}.pdf"
            return pdf_bytes, filename
        except Exception:
            logger.exception("Failed to generate annual growth development PDF for %s", year)
            raise

    def generate_all_analytics_reports_pdf(
        self,
        year: int,
        month: Optional[int] = None,
        header_lines: Optional[list] = None,
        watermark: Optional[str] = None,
        left_image: Optional[str] = None,
        right_image: Optional[str] = None,
        generated_by_name: Optional[str] = None,
        generated_by_role: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate consolidated PDF with all monthly reports (if month provided) or all annual reports.
        
        If month is provided: includes monthly immunization, visit completion, and growth/nutrition.
        If month is None: includes all annual reports (screening risk, immunization performance, growth development).
        """
        try:
            if not self._reports_query:
                raise ValueError("ChildReportsQuery not injected into service")

            sections = []
            
            if month:
                # Monthly reports consolidated
                title = f"Monthly Child Health Analytics - {year}/{month:02d}"
                
                # 1. Immunization Coverage
                imm_data = self._reports_query.get_monthly_immunization_coverage(year, month)
                coverage = imm_data.get('coverage_summary') or {}
                if coverage:
                    summary_lines = [
                        f"Total Children: {_fmt(coverage.get('total_children'))}",
                        f"Children Vaccinated: {_fmt(coverage.get('children_vaccinated'))}",
                        f"Coverage Percentage: {_fmt(coverage.get('coverage_percentage'))}%",
                    ]
                    sections.append({"heading": "Immunization Coverage Summary", "content": "<br/>".join(summary_lines)})
                
                type_cov = imm_data.get('type_coverage') or []
                if type_cov:
                    table = [["Vaccine Type", "Doses Given", "Children Receiving"]]
                    for tc in type_cov:
                        table.append([tc.get('vaccine_type',''), str(tc.get('doses_given',0)), str(tc.get('children_receiving',0))])
                    table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                    sections.append({"heading": "Immunization Type Coverage", "content": table_wrapped})
                
                # 2. Visit Completion
                visit_data = self._reports_query.get_monthly_visit_completion(year, month)
                visit_summary = visit_data.get('visit_summary') or {}
                if visit_summary:
                    visit_lines = [
                        f"Total Scheduled: {_fmt(visit_summary.get('total_scheduled'))}",
                        f"Completed Visits: {_fmt(visit_summary.get('completed_visits'))}",
                        f"Missed Visits: {_fmt(visit_summary.get('missed_visits'))}",
                        f"Completion Rate: {_fmt(visit_summary.get('completion_rate'))}%",
                    ]
                    sections.append({"heading": "Visit Completion Summary", "content": "<br/>".join(visit_lines)})
                
                worker = visit_data.get('worker_performance') or []
                if worker:
                    table = [["Worker Name", "Visits Handled", "Completed", "Completion Rate %"]]
                    for w in worker:
                        table.append([w.get('worker_name',''), str(w.get('visits_handled',0)), str(w.get('completed',0)), str(w.get('completion_rate',0))])
                    table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                    sections.append({"heading": "Worker Performance", "content": table_wrapped})
                
                # 3. Growth & Nutrition
                growth_data = self._reports_query.get_monthly_growth_nutrition(year, month)
                nutrition = growth_data.get('nutrition_summary') or {}
                if nutrition:
                    nutrition_lines = [
                        f"Total Monitored: {_fmt(nutrition.get('total_monitored'))}",
                        f"Underweight Cases: {_fmt(nutrition.get('underweight_count'))}",
                        f"Stunted Cases: {_fmt(nutrition.get('stunted_count'))}",
                        f"Average Weight: {_fmt(nutrition.get('avg_weight'))} kg",
                        f"Average Height: {_fmt(nutrition.get('avg_height'))} cm",
                    ]
                    sections.append({"heading": "Growth & Nutrition Summary", "content": "<br/>".join(nutrition_lines)})
                
                hotspot = growth_data.get('hotspot_analysis') or []
                if hotspot:
                    table = [["Purok", "Children Monitored", "Underweight", "Stunted", "Malnutrition Rate %"]]
                    for h in hotspot:
                        table.append([h.get('purok',''), str(h.get('children_monitored',0)), str(h.get('underweight_cases',0)), str(h.get('stunted_cases',0)), str(h.get('malnutrition_rate',0))])
                    table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                    sections.append({"heading": "Geographic Hotspots", "content": table_wrapped})
                
                filename = f"monthly_analytics_{year}_{month:02d}.pdf"
            else:
                # Annual reports consolidated
                title = f"Annual Child Health Analytics - {year}"
                
                # 1. Screening & Risk
                risk_data = self._reports_query.get_annual_screening_risk(year)
                risk_summary = risk_data.get('risk_summary') or {}
                if risk_summary:
                    risk_lines = [
                        f"Total Screenings: {_fmt(risk_summary.get('total_screenings'))}",
                        f"Low Birth Weight Cases: {_fmt(risk_summary.get('low_birth_weight_cases'))}",
                        f"LBW Rate: {_fmt(risk_summary.get('lbw_rate'))}%",
                        f"Anemia Supplemented: {_fmt(risk_summary.get('anemia_supplemented'))}",
                    ]
                    sections.append({"heading": "Screening & Risk Summary", "content": "<br/>".join(risk_lines)})
                
                trends = risk_data.get('monthly_trends') or []
                if trends:
                    table = [["Month", "Screenings", "LBW Cases", "Anemia Cases", "LBW Rate %"]]
                    for t in trends:
                        table.append([str(t.get('month','')), str(t.get('screenings_count',0)), str(t.get('lbw_cases',0)), str(t.get('anemia_cases',0)), str(t.get('lbw_rate_pct',0))])
                    table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                    sections.append({"heading": "Monthly Risk Trends", "content": table_wrapped})
                
                # 2. Immunization Performance
                imm_perf_data = self._reports_query.get_annual_immunization_performance(year)
                coverage = imm_perf_data.get('vaccine_coverage') or []
                if coverage:
                    table = [["Vaccine", "Doses Administered", "Children Immunized", "Coverage Rate %"]]
                    for c in coverage:
                        table.append([c.get('vaccine_name',''), str(c.get('doses_administered',0)), str(c.get('children_immunized',0)), str(c.get('coverage_rate',0))])
                    table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                    sections.append({"heading": "Full-Year Vaccine Coverage", "content": table_wrapped})
                
                herd = imm_perf_data.get('herd_immunity') or []
                if herd:
                    table = [["Vaccine Type", "Coverage %", "Status"]]
                    for h in herd:
                        table.append([h.get('vaccine_type',''), str(h.get('coverage_percentage',0)), h.get('herd_immunity_status','')])
                    table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                    sections.append({"heading": "Herd Immunity Status", "content": table_wrapped})
                
                # 3. Growth & Development
                growth_dev_data = self._reports_query.get_annual_growth_development(year)
                age_groups = growth_dev_data.get('growth_by_age_group') or []
                if age_groups:
                    table = [["Age Group", "Children", "Avg Weight", "Avg Height"]]
                    for ag in age_groups:
                        table.append([ag.get('age_group',''), str(ag.get('children_count',0)), str(ag.get('avg_weight',0)), str(ag.get('avg_height',0))])
                    table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                    sections.append({"heading": "Growth by Age Group", "content": table_wrapped})
                
                purok = growth_dev_data.get('purok_disparities') or []
                if purok:
                    table = [["Purok", "Children", "Malnutrition Cases", "Malnutrition Rate %"]]
                    for p in purok:
                        table.append([p.get('purok',''), str(p.get('children_count',0)), str(p.get('malnutrition_cases',0)), str(p.get('malnutrition_rate',0))])
                    table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in table]
                    sections.append({"heading": "Purok-Level Disparities", "content": table_wrapped})
                
                filename = f"annual_analytics_{year}.pdf"
            
            header_lines_to_use = header_lines or self._default_header_lines()
            watermark_to_use = watermark or "CONFIDENTIAL HEALTH INFORMATION"
            left_img = MaternalReportHelpers.resolve_image(left_image) if left_image else None
            right_img = MaternalReportHelpers.resolve_image(right_image) if right_image else None

            pdf_bytes = self._pdf.generate(
                title=title,
                header_lines=header_lines_to_use,
                header_color="#002060",
                left_image_path=left_img,
                right_image_path=right_img,
                watermark_text=watermark_to_use,
                sections=sections,
                additional_signatory_name=generated_by_name,
                additional_signatory_role=generated_by_role,
            )

            return pdf_bytes, filename
        except Exception:
            logger.exception("Failed to generate consolidated analytics PDF for year=%s, month=%s", year, month)
            raise

    def _default_header_lines(self) -> list:
        """Return default header lines for child health reports."""
        return [
            ("Republic of the Philippines", 14),
            ("Barangay Health Center", 14),
            ("BARANGAY SEÑOR SANTO NIÑO", 14),
            ("032 Legaspi Street, Cebu City", 11),
        ]
