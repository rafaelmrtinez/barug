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

    def generate_business_detail_pdf(
        self,
        business_dto: Any,
        generated_by_name: Optional[str] = None,
        generated_by_role: Optional[str] = None,
    ) -> Tuple[bytes, str]:
        """Generate PDF bytes for a single business detail report."""
        
        try:
            business = dict(business_dto.business or {})
            owner = dict(business_dto.owner or {})
            
            # Construct full name from components
            name_parts = [
                owner.get('first_name'),
                owner.get('middle_name'),
                owner.get('last_name'),
                owner.get('suffix')
            ]
            owner_full_name = ' '.join(filter(None, name_parts)) or None
            
            # Construct full address from components
            address_parts = [
                owner.get('street'),
                owner.get('sitio_purok'),
                owner.get('barangay'),
                owner.get('city')
            ]
            owner_full_address = ', '.join(filter(None, address_parts)) or None
            
            # Debug: log business keys to find operating hours field
            logger.info(f"Business data keys: {list(business.keys())}")
            logger.info(f"Business operating_hours: {business.get('operating_hours')}")
            logger.info(f"Business operating_hour: {business.get('operating_hour')}")
            
            # Parse operating days for display
            DAY_MAP = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}
            operating_days_str = (business.get("operating_days") or "").strip()
            days = [d.strip() for d in operating_days_str.split(",")] if operating_days_str else []
            operating_days_start_name = days[0] if days else None
            operating_days_end_name = days[-1] if days else None
            
            # Map numeric day values to day names for display
            opt_days_start = business.get('operating_days_start')
            opt_days_end = business.get('operating_days_end')
            if opt_days_start and not operating_days_start_name:
                operating_days_start_name = DAY_MAP.get(opt_days_start)
            if opt_days_end and not operating_days_end_name:
                operating_days_end_name = DAY_MAP.get(opt_days_end)
            
            # Build sections
            sections = []

            # SECTION 1: Business Owner
            sections.append({
                "heading": "Business Owner",
                "content": [
                    [Paragraph("Owner Name", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(owner_full_name), TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Person Code", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(owner.get('person_code')), TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Residential Status", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(owner.get('residential_status')), TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Sex", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(owner.get('sex')), TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Date of Birth", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(owner.get('birthdate')), TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Address", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(owner_full_address), TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Civil Status", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(owner.get('civil_status')), TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Nationality", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(owner.get('nationality')), TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Religion", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(owner.get('religion')), TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Mobile", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(owner.get('mobile_num')), TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Email", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(owner.get('email')), TABLE_PARAGRAPH_STYLE)],
                ]
            })

            # SECTION 2: Business Identity
            sections.append({
                "heading": "Business Identity",
                "content": [
                    [Paragraph("Business ID", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(business.get('business_id')), TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Business Name", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(business.get('business_name')), TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Business Status", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(business.get('business_status')), TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Ownership Type", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(business.get('ownership_type')), TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Business Category", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(business.get('business_category')), TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Nature of Business", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(business.get('business_nature')), TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Date Established", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(business.get('date_established')), TABLE_PARAGRAPH_STYLE)],
                ]
            })

            # SECTION 3: Registration & Financials
            capital = business.get('capital_invested')
            prev_sales = business.get('prev_year_gross_sales')
            monthly_income = business.get('mnthly_gross_incom_est')
            
            sections.append({
                "heading": "Registration & Financials",
                "content": [
                    [Paragraph("Capital Invested", TABLE_PARAGRAPH_STYLE), Paragraph(f"PHP {_fmt(capital)}" if capital else "N/A", TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Previous Year Total Gross Sales", TABLE_PARAGRAPH_STYLE), Paragraph(f"PHP {_fmt(prev_sales)}" if prev_sales else "N/A", TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Monthly Gross Income Estimate", TABLE_PARAGRAPH_STYLE), Paragraph(f"PHP {_fmt(monthly_income)}" if monthly_income else "N/A", TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("DTI/SEC Registration Number", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(business.get('dti_reg_num')), TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Number of Employees", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(business.get('num_of_employees')), TABLE_PARAGRAPH_STYLE)],
                ]
            })

            # SECTION 4: Location
            sections.append({
                "heading": "Location",
                "content": [
                    [Paragraph("Business Address", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(business.get('business_address')), TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Location Description", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(business.get('description')), TABLE_PARAGRAPH_STYLE)],
                ]
            })

            # SECTION 5: Operating Schedule
            operating_days_display = "N/A"
            if operating_days_start_name and operating_days_end_name:
                operating_days_display = f"{operating_days_start_name} - {operating_days_end_name}"
            elif operating_days_start_name:
                operating_days_display = operating_days_start_name
            
            # Check various possible field names for operating hours
            operating_hours = (
                business.get('operating_hours') or 
                business.get('operating_hour') or
                business.get('operating_hours_start') or 
                business.get('opt_start')
            )
            operating_hours_display = _fmt(operating_hours) if operating_hours else "N/A"
            
            logger.info(f"Operating hours final value: {operating_hours_display}")
            
            sections.append({
                "heading": "Operating Schedule",
                "content": [
                    [Paragraph("Operating Days", TABLE_PARAGRAPH_STYLE), Paragraph(operating_days_display, TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Operating Hours", TABLE_PARAGRAPH_STYLE), Paragraph(operating_hours_display, TABLE_PARAGRAPH_STYLE)],
                ]
            })

            # SECTION 6: Metadata
            sections.append({
                "heading": "Metadata",
                "content": [
                    [Paragraph("Created At", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(business.get('created_at')), TABLE_PARAGRAPH_STYLE)],
                    [Paragraph("Updated At", TABLE_PARAGRAPH_STYLE), Paragraph(_fmt(business.get('updated_at')), TABLE_PARAGRAPH_STYLE)],
                ]
            })

            # Build document title
            business_name = business.get('business_name', 'Business')
            business_id = business.get('business_id', '')
            title = f"Business Details - {business_name}"
            
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
            filename = f"business_detail_{business_id}_{timestamp}.pdf"

            return pdf_bytes, filename

        except Exception:
            logger.exception("Failed to generate business detail PDF")
            raise