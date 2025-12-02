"""
Household History Report Service
Generates PDF reports for household history data.
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


class HouseholdHistoryReportService:
    """Service to generate household history reports."""

    def __init__(self, pdf_generator: Optional[PdfGeneratorH] = None):
        self._pdf = pdf_generator or PdfGeneratorH()

    def generate_household_history_pdf(
        self,
        household_data: List[Any],
        quarter: int,
        year: int,
        search_term: Optional[str] = None,
        house_type: Optional[str] = None,
        house_ownership: Optional[str] = None,
        generated_by_name: Optional[str] = None,
        generated_by_role: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate PDF bytes for household history report."""
        
        try:
            # Build sections
            sections = []

            # Household table
            if household_data:
                household_table = [
                    ["Household No", "Head", "Address", "Type", "Ownership", "Created Date"]
                ]
                
                for household in household_data:
                    # Build address
                    address_parts = []
                    if household.get('street_name'):
                        address_parts.append(household['street_name'])
                    if household.get('purok_sitio_name'):
                        address_parts.append(household['purok_sitio_name'])
                    if household.get('barangay_name'):
                        address_parts.append(f"BRGY {household['barangay_name']}")
                    if household.get('city_name'):
                        address_parts.append(household['city_name'])
                    
                    address = ", ".join(filter(None, address_parts)) if address_parts else "N/A"
                    
                    # Format created date
                    created_date = household.get('created_date')
                    if created_date:
                        if hasattr(created_date, 'strftime'):
                            created_date = created_date.strftime('%b %d, %Y')
                        else:
                            created_date = str(created_date)[:10]  # Get YYYY-MM-DD
                    else:
                        created_date = "N/A"
                    
                    household_table.append([
                        _fmt(household.get('household_num')),
                        _fmt(household.get('householdhead_name')),
                        _fmt(address),
                        _fmt(household.get('house_type_name')),
                        _fmt(household.get('house_ownership_name')),
                        created_date
                    ])
                
                # Wrap table cells in Paragraphs
                household_table_wrapped = [
                    [Paragraph(_fmt(cell), TABLE_PARAGRAPH_STYLE) for cell in row] 
                    for row in household_table
                ]
                sections.append({"content": household_table_wrapped})
            else:
                sections.append({
                    "content": f"No household history records found for Q{quarter} {year}."
                })

            # Build document title
            title = f"Household History - Q{quarter} {year}"
            
            # Build subtitle with filters
            subtitle_parts = []
            if search_term:
                subtitle_parts.append(f"Search: {search_term}")
            if house_type:
                subtitle_parts.append(f"House Type: {house_type}")
            if house_ownership:
                subtitle_parts.append(f"Ownership: {house_ownership}")
            
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
            filename = f"household_history_Q{quarter}_{year}_{timestamp}.pdf"

            return pdf_bytes, filename

        except Exception:
            logger.exception("Failed to generate household history PDF")
            raise
