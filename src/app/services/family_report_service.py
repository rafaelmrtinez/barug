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
    fontSize=9,
    leading=11,
    alignment=TA_CENTER,
)

def _fmt(value) -> str:
    """Format a value for display in the PDF."""
    if value is None:
        return "N/A"
    if isinstance(value, str):
        s = value.strip()
        return s if s != "" else "N/A"
    if isinstance(value, dict):
        return str(value)
    return str(value)

class FamilyReportService:
    """Service to generate family list reports."""

    def __init__(self, pdf_generator: Optional[PdfGeneratorH] = None):
        self._pdf = pdf_generator or PdfGeneratorH()

    def generate_family_list_pdf(
        self,
        family_data: List[Any],
        search_term: Optional[str] = None,
        household_type: Optional[str] = None,
        nhts_status: Optional[str] = None,
        indigent_status: Optional[str] = None,
        generated_by_name: Optional[str] = None,
        generated_by_role: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate PDF bytes for family list report."""
        
        try:
            # Build sections
            sections = []

            # Family table
            if family_data:
                family_table = [["Family No", "UFC No", "Family Head", "Household", "Type", "NHTS", "Indigent"]]
                
                for family in family_data:
                    # Handle both dict and object access
                    if isinstance(family, dict):
                        family_num = family.get('family_num', '')
                        ufc_num = family.get('ufc_num', '')
                        family_head_name = family.get('family_head_name', '')
                        household_num = family.get('household_num', '')
                        household_type = family.get('household_type', '')
                        nhts = family.get('nhts_status', '')
                        indigent = family.get('indigent_status', '')
                    else:
                        family_num = getattr(family, 'family_num', '')
                        ufc_num = getattr(family, 'ufc_num', '')
                        family_head_name = getattr(family, 'family_head_name', '')
                        household_num = getattr(family, 'household_num', '')
                        household_type = getattr(family, 'household_type', '')
                        nhts = getattr(family, 'nhts_status', '')
                        indigent = getattr(family, 'indigent_status', '')
                    
                    family_table.append([
                        _fmt(family_num),
                        _fmt(ufc_num),
                        _fmt(family_head_name),
                        _fmt(household_num),
                        _fmt(household_type),
                        _fmt(nhts),
                        _fmt(indigent)
                    ])
                
                # Wrap table cells in Paragraphs
                family_table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in family_table]
                sections.append({"content": family_table_wrapped})
            else:
                sections.append({"content": "No families found matching the criteria."})

            # Build document title
            title = "Family List"
            
            # Use default header lines
            header_lines = [
                ("Republic of the Philippines", 14),
                ("Barangay Health Center", 14),
                ("BARANGAY SEÑOR SANTO NIÑO", 14),
                ("032 Legaspi Street, Cebu City", 11),
            ]

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
            filename = f"family_list_{timestamp}.pdf"

            return pdf_bytes, filename

        except Exception:
            logger.exception("Failed to generate family list PDF")
            raise
