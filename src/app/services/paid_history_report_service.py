from typing import Optional, Tuple, List, Dict, Any
from datetime import date
import logging

from src.infra.utilities.pdf_generator_h import PdfGeneratorH
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER

logger = logging.getLogger(__name__)

# Paragraph style for table cells
TABLE_PARAGRAPH_STYLE = ParagraphStyle(
    "TableBody",
    fontName="Helvetica",
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
        # Remove any non-ASCII characters that might cause rendering issues
        s = ''.join(char for char in s if ord(char) < 128 or char.isalnum() or char in ' .,:-/')
        return s if s != "" else "N/A"
    return str(value)

class PaidHistoryReportService:
    """Service to generate paid history PDF reports."""

    def __init__(self, pdf_generator: PdfGeneratorH):
        self._pdf = pdf_generator

    def generate_paid_history_pdf(
        self,
        business_dto: Any,
        paid_rows: List[Dict[str, Any]],
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        year_filter: Optional[str] = None,
        generated_by_name: Optional[str] = None,
        generated_by_role: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate PDF bytes for paid history report."""
        
        try:
            business = dict(business_dto.business or {})
            
            # Build table data
            table_data = []
            table_data.append([
                Paragraph("Year", TABLE_PARAGRAPH_STYLE),
                Paragraph("OR Number", TABLE_PARAGRAPH_STYLE),
                Paragraph("Paid On", TABLE_PARAGRAPH_STYLE),
                Paragraph("Status", TABLE_PARAGRAPH_STYLE),
            ])
            
            for row in paid_rows:
                paid_on_str = "N/A"
                if row.get('paid_on'):
                    try:
                        paid_date = row['paid_on']
                        if isinstance(paid_date, str):
                            paid_on_str = paid_date.split('T')[0]  # Extract YYYY-MM-DD
                        else:
                            paid_on_str = str(paid_date)
                    except Exception:
                        paid_on_str = str(row['paid_on'])
                
                table_data.append([
                    Paragraph(str(row.get('period_year', 'N/A')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(_fmt(row.get('or_number')), TABLE_PARAGRAPH_STYLE),
                    Paragraph(paid_on_str, TABLE_PARAGRAPH_STYLE),
                    Paragraph("PAID", TABLE_PARAGRAPH_STYLE),
                ])
            
            # Build sections
            sections = []
            
            # Add filter info if applicable
            filter_info = []
            if year_filter:
                filter_info.append(f"Year: {year_filter}")
            if from_date and to_date:
                filter_info.append(f"Period: {from_date} to {to_date}")
            elif from_date:
                filter_info.append(f"From: {from_date}")
            elif to_date:
                filter_info.append(f"To: {to_date}")
            
            if filter_info:
                sections.append({
                    "heading": "Filters Applied",
                    "content": " | ".join(filter_info)
                })
            
            # Add paid history table
            sections.append({
                "heading": "Paid History Records",
                "content": table_data
            })
            
            # Build document title
            business_name = business.get('business_name', 'Business')
            business_id = business.get('business_id', '')
            title = f"Paid History Report - {business_name}"
            
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
            filename = f"paid_history_{business_id}_{timestamp}.pdf"

            return pdf_bytes, filename

        except Exception:
            logger.exception("Failed to generate paid history PDF")
            raise
