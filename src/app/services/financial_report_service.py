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

class FinancialReportService:
    """Service to generate financial report."""

    def __init__(self, pdf_generator: Optional[PdfGeneratorH] = None):
        self._pdf = pdf_generator or PdfGeneratorH()

    def generate_financial_report_pdf(
        self,
        or_data: List[Any],
        search_term: Optional[str] = None,
        payment_method: Optional[str] = None,
        month: Optional[str] = None,
        year: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        generated_by_name: Optional[str] = None,
        generated_by_role: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate PDF bytes for financial report."""
        
        try:
            # Build sections
            sections = []

            # Add filter info header if filters are applied
            filter_info = []
            if search_term:
                filter_info.append(f"Search: {search_term}")
            if payment_method:
                payment_methods = {"1": "CASH", "2": "GCASH", "3": "CARD", "4": "WAIVED", "5": "ONLINE GCASH"}
                method_name = payment_methods.get(payment_method, payment_method)
                filter_info.append(f"Payment Method: {method_name}")
            if month and year:
                months = {
                    "1": "January", "2": "February", "3": "March", "4": "April",
                    "5": "May", "6": "June", "7": "July", "8": "August",
                    "9": "September", "10": "October", "11": "November", "12": "December"
                }
                month_name = months.get(month, month)
                filter_info.append(f"Period: {month_name} {year}")
            elif year:
                filter_info.append(f"Year: {year}")
            elif date_from and date_to:
                filter_info.append(f"Date Range: {date_from} to {date_to}")
            
            if filter_info:
                sections.append({"content": " | ".join(filter_info), "style": "Heading2"})

            # OR table
            if or_data:
                or_table = [["OR Number", "Payment Method", "Amount", "Purpose", "Issued By", "Issued At"]]
                total_amount = 0.0
                
                for or_record in or_data:
                    amount = getattr(or_record, 'amount_paid', 0)
                    try:
                        total_amount += float(amount or 0)
                    except (ValueError, TypeError):
                        pass
                    
                    or_table.append([
                        _fmt(getattr(or_record, 'or_number', '')),
                        _fmt(getattr(or_record, 'payment_method', '')),
                        _fmt(amount),
                        _fmt(getattr(or_record, 'purpose', '')),
                        _fmt(getattr(or_record, 'issued_by', '')),
                        _fmt(getattr(or_record, 'issued_at', ''))
                    ])
                
                # Add total row
                or_table.append([
                    "TOTAL", "", f"₱{total_amount:,.2f}", "", "", ""
                ])
                
                # Wrap table cells in Paragraphs
                or_table_wrapped = [[Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] for row in or_table]
                sections.append({"content": or_table_wrapped})
            else:
                sections.append({"content": "No official receipts found matching the criteria."})

            # Build document title
            title = "Financial Report"
            
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
            filename = f"financial_report_{timestamp}.pdf"

            return pdf_bytes, filename

        except Exception:
            logger.exception("Failed to generate financial report PDF")
            raise