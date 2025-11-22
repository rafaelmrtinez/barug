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

class BusinessReportService:
    """Service to generate business list reports."""

    def __init__(self, pdf_generator: Optional[PdfGeneratorH] = None):
        self._pdf = pdf_generator or PdfGeneratorH()

    def generate_business_list_pdf(
        self,
        business_data: List[Any],
        search_term: Optional[str] = None,
        b_category: Optional[str] = None,
        ownership_type: Optional[str] = None,
        status: Optional[str] = None,
        generated_by_name: Optional[str] = None,
        generated_by_role: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate PDF bytes for business list report."""
        
        try:
            # Build sections
            sections = []

            # Business table
            if business_data:
                business_table = [["Business ID", "Business Name", "Category", "Nature", "Ownership", "Owner", "Address", "Status"]]
                
                for business in business_data:
                    business_table.append([
                        _fmt(getattr(business, 'business_id', '')),
                        _fmt(getattr(business, 'business_name', '')),
                        _fmt(getattr(business, 'business_category_name', '')),
                        _fmt(getattr(business, 'business_nature', '')),
                        _fmt(getattr(business, 'ownership_type_name', '')),
                        _fmt(getattr(business, 'business_owner_name', '')),
                        _fmt(getattr(business, 'business_address', '')),
                        _fmt(getattr(business, 'business_status_name', ''))
                    ])
                
                # Wrap table cells in Paragraphs
                business_table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in business_table]
                sections.append({"content": business_table_wrapped})
            else:
                sections.append({"content": "No businesses found matching the criteria."})

            # Build document title
            title = "Business List"
            
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
            filename = f"business_list_{timestamp}.pdf"

            return pdf_bytes, filename

        except Exception:
            logger.exception("Failed to generate business list PDF")
            raise