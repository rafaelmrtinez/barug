from typing import Optional

from src.infra.utilities.pdf_generator import PdfGenerator
from src.infra.utilities.age_calculator import AgeCalculator
from src.infra.repositories.child_report_repository import ChildReportRepository
from src.infra.exceptions.child_health_record_exceptions import ChildHealthRecordException
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

    def __init__(self, repository: ChildReportRepository, pdf_generator: Optional[PdfGenerator] = None):
        self._repo = repository
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
    ) -> bytes:
        try:
            payload = self._repo.assemble_report_payload(child_record_id)

            if not payload.get("patient_info"):
                logger.error("Child health record %s not found", child_record_id)
                raise ChildHealthRecordException("Child health record not found")

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

            return pdf_bytes
        except Exception:
            logger.exception("Failed to generate child summary PDF for child record %s", child_record_id)
            raise
