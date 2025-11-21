from typing import Optional, Tuple, List, Dict, Any
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

class ResidentReportService:
    """Service to generate resident list reports."""

    def __init__(self, pdf_generator: Optional[PdfGeneratorH] = None):
        self._pdf = pdf_generator or PdfGeneratorH()

    def generate_residents_list_pdf(
        self,
        residents_data: List[Any],
        search_term: Optional[str] = None,
        purok_sitio: Optional[str] = None,
        generated_by_name: Optional[str] = None,
        generated_by_role: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate PDF bytes for residents list report."""
        
        try:
            # Build sections
            sections = []

            # Residents table
            if residents_data:
                residents_table = [["Resident Code", "Full Name", "Address", "Mobile Number", "Email"]]
                
                for resident in residents_data:
                    
                    residents_table.append([
                        _fmt(getattr(resident, 'person_code', '')),
                        _fmt(getattr(resident, 'full_name', '')),
                        _fmt(getattr(resident, 'address', '')),
                        _fmt(getattr(resident, 'mob_num', '')),
                        _fmt(getattr(resident, 'email', ''))
                    ])
                
                # Wrap table cells in Paragraphs
                residents_table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in residents_table]
                sections.append({"content": residents_table_wrapped})
            else:
                sections.append({"content": "No residents found matching the criteria."})

            # Build document title
            title = "Residents List"
            
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
            filename = f"residents_list_{timestamp}.pdf"

            return pdf_bytes, filename

        except Exception:
            logger.exception("Failed to generate residents list PDF")
            raise