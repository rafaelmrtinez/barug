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

class HouseholdReportService:
    """Service to generate household list reports."""

    def __init__(self, pdf_generator: Optional[PdfGeneratorH] = None):
        self._pdf = pdf_generator or PdfGeneratorH()

    def generate_household_list_pdf(
        self,
        household_data: List[Any],
        search_term: Optional[str] = None,
        house_type: Optional[str] = None,
        house_ownership: Optional[str] = None,
        generated_by_name: Optional[str] = None,
        generated_by_role: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate PDF bytes for household list report."""
        
        try:
            # Build sections
            sections = []

            # Household table
            if household_data:
                household_table = [["Household No", "Head", "Address", "Type", "Ownership"]]
                
                for household in household_data:
                    household_table.append([
                        _fmt(getattr(household, 'household_no', '')),
                        _fmt(getattr(household, 'head_name', '')),
                        _fmt(getattr(household, 'address', '')),
                        _fmt(getattr(household, 'house_type', '')),
                        _fmt(getattr(household, 'house_ownership', ''))
                    ])
                
                # Wrap table cells in Paragraphs
                household_table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in household_table]
                sections.append({"content": household_table_wrapped})
            else:
                sections.append({"content": "No households found matching the criteria."})

            # Build document title
            title = "Household List"
            
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
            filename = f"household_list_{timestamp}.pdf"

            return pdf_bytes, filename

        except Exception:
            logger.exception("Failed to generate household list PDF")
            raise