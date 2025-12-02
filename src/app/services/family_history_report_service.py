"""
Family History Report Service
Generates PDF reports for family history data.
"""

from typing import Optional, Tuple, List, Any
import logging

from src.infra.utilities.pdf_generator_h import PdfGeneratorH
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER

logger = logging.getLogger(__name__)

# Paragraph style for table cells
TABLE_PARAGRAPH_STYLE = ParagraphStyle(
    "TableBody",
    fontName="Times-Roman",
    fontSize=10,
    leading=12,
    alignment=TA_CENTER,
)

def _fmt(value) -> str:
    """Format a value for display in the PDF."""
    if value is None:
        return "N/A"
    if isinstance(value, str):
        s = value.strip()
        return s if s != "" else "N/A"
    return str(value)


class FamilyHistoryReportService:
    """Service to generate family history reports."""

    def __init__(self, pdf_generator: Optional[PdfGeneratorH] = None):
        self._pdf = pdf_generator or PdfGeneratorH()

    def generate_family_history_pdf(
        self,
        family_data: List[Any],
        quarter: int,
        year: int,
        search_term: Optional[str] = None,
        household_type: Optional[str] = None,
        nhts_status: Optional[str] = None,
        indigent_status: Optional[str] = None,
        generated_by_name: Optional[str] = None,
        generated_by_role: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate PDF bytes for family history report."""
        
        try:
            # Build sections
            sections = []

            # Family table
            if family_data:
                family_table = [
                    ["Family No", "UFC No", "Family Head", "Household", "Type", "NHTS", "Indigent", "Created Date"]
                ]
                
                for family in family_data:
                    # Format created date
                    created_date = family.get('created_date')
                    if created_date:
                        if hasattr(created_date, 'strftime'):
                            created_date = created_date.strftime('%b %d, %Y')
                        else:
                            created_date = str(created_date)[:10]  # Get YYYY-MM-DD
                    else:
                        created_date = "N/A"
                    
                    family_table.append([
                        _fmt(family.get('family_num')),
                        _fmt(family.get('ufc_num')),
                        _fmt(family.get('family_head_name')),
                        _fmt(family.get('household_num')),
                        _fmt(family.get('household_type_name')),
                        _fmt(family.get('nhts_status_name')),
                        _fmt(family.get('indigent_status_name')),
                        created_date
                    ])
                
                # Wrap table cells in Paragraphs
                family_table_wrapped = [
                    [Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] 
                    for row in family_table
                ]
                sections.append({"content": family_table_wrapped})
            else:
                sections.append({
                    "content": f"No family history records found for Q{quarter} {year}."
                })

            # Build document title
            title = f"Family History - Q{quarter} {year}"
            
            # Build subtitle with filters
            subtitle_parts = []
            if search_term:
                subtitle_parts.append(f"Search: {search_term}")
            if household_type:
                subtitle_parts.append(f"Household Type: {household_type}")
            if nhts_status:
                subtitle_parts.append(f"NHTS: {nhts_status}")
            if indigent_status:
                subtitle_parts.append(f"Indigent: {indigent_status}")
            
            subtitle = " | ".join(subtitle_parts) if subtitle_parts else None

            # Use default header lines
            header_lines = [
                ("Republic of the Philippines", 14),
                ("Barangay Health Center", 14),
                ("BARANGAY SEÑOR SANTO NIÑO", 14),
                ("032 Legaspi Street, Cebu City", 11),
            ]
            
            if subtitle:
                header_lines.append((subtitle, 10))

            pdf_bytes = self._pdf.generate(
                title=title,
                header_lines=header_lines,
                header_color="#002060",
                watermark_text="OFFICIAL BARANGAY DOCUMENT",
                sections=sections,
                additional_signatory_name=generated_by_name,
                additional_signatory_role=generated_by_role,
            )
            
            # Build filename
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"family_history_Q{quarter}_{year}_{timestamp}.pdf"

            return pdf_bytes, filename

        except Exception:
            logger.exception("Failed to generate family history PDF")
            raise
