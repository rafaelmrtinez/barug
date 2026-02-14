from django.http import HttpResponse
from django.db import connection
from authentication.guards import session_login_required, role_required
from pypdf import PdfReader, PdfWriter
from io import BytesIO
from datetime import datetime
import pytz
import os
from django.conf import settings

LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}

@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def generate_blotter_pdf(request, report_id: int):
    """Generate filled PDF for lupon blotter file using PyMuPDF overlay"""
    
    # Get report data
    with connection.cursor() as cur:
        cur.execute("""
            SELECT 
                br.blotter_report_id,
                br.incident_subject,
                br.incident_desc,
                br.incident_date,
                br.incident_time,
                br.date_time_reported,
                STRING_AGG(DISTINCT TRIM(CONCAT_WS(' ', comp.first_name, comp.middle_name, comp.last_name, comp.suffix)), ', ') as complainant_names,
                STRING_AGG(DISTINCT COALESCE(comp_addr.street, '') || ' ' || COALESCE(comp_ps.purok_sitio_name, '') || ' ' || COALESCE(comp_addr.barangay, '') || ' ' || COALESCE(comp_addr.city, ''), ', ') as complainant_addresses,
                STRING_AGG(DISTINCT COALESCE(comp.mobile_num, ''), ', ') as complainant_contacts,
                STRING_AGG(DISTINCT TRIM(CONCAT_WS(' ', resp.first_name, resp.middle_name, resp.last_name, resp.suffix)), ', ') as respondent_names,
                STRING_AGG(DISTINCT COALESCE(resp_addr.street, '') || ' ' || COALESCE(resp_ps.purok_sitio_name, '') || ' ' || COALESCE(resp_addr.barangay, '') || ' ' || COALESCE(resp_addr.city, ''), ', ') as respondent_addresses,
                STRING_AGG(DISTINCT COALESCE(resp.mobile_num, ''), ', ') as respondent_contacts
            FROM blotter_report br
            LEFT JOIN complainant_report cr ON cr.blotter_report_id = br.blotter_report_id
            LEFT JOIN person comp ON comp.person_id = cr.person_id
            LEFT JOIN addresss comp_addr ON comp_addr.address_id = comp.address_id
            LEFT JOIN purok_sitio comp_ps ON comp_ps.purok_sitio_id = comp_addr.purok_sitio_id
            LEFT JOIN respondent_report rr ON rr.blotter_report_id = br.blotter_report_id
            LEFT JOIN person resp ON resp.person_id = rr.person_id
            LEFT JOIN addresss resp_addr ON resp_addr.address_id = resp.address_id
            LEFT JOIN purok_sitio resp_ps ON resp_ps.purok_sitio_id = resp_addr.purok_sitio_id
            WHERE br.blotter_report_id = %s
            GROUP BY br.blotter_report_id, br.incident_subject, br.incident_desc, br.incident_date, br.incident_time, br.date_time_reported
        """, [report_id])
        
        report_data = cur.fetchone()
        if not report_data:
            return HttpResponse("Report not found", status=404)
        
        # Get Barangay Captain and Secretary
        cur.execute("""
            SELECT TRIM(CONCAT_WS(' ', p.first_name, p.middle_name, p.last_name, p.suffix)) as name, r.role_name
            FROM staff s
            JOIN person p ON p.person_id = s.person_id
            JOIN rolee r ON r.role_id = s.role_id
            WHERE r.role_name IN ('BARANGAY CAPTAIN', 'BARANGAY SECRETARY')
            LIMIT 2
        """)
        officials = {row[1]: row[0] for row in cur.fetchall()}
    
    # Unpack data
    (report_id, incident_subject, incident_desc, incident_date, incident_time,
     date_time_reported_raw, complainant_names, complainant_addresses, complainant_contacts,
     respondent_names, respondent_addresses, respondent_contacts) = report_data
    
    # Convert timestamp to Philippine timezone using Python
    date_time_reported = ""
    if date_time_reported_raw:
        manila_tz = pytz.timezone('Asia/Manila')
        if date_time_reported_raw.tzinfo is None:
            # If naive, assume UTC
            utc_dt = pytz.utc.localize(date_time_reported_raw)
        else:
            # If aware, convert to UTC first
            utc_dt = date_time_reported_raw.astimezone(pytz.utc)
        manila_dt = utc_dt.astimezone(manila_tz)
        date_time_reported = manila_dt.strftime('%B %d, %Y %I:%M %p')
        print(f"\n=== DEBUG ===")
        print(f"Raw: {date_time_reported_raw}")
        print(f"Manila: {manila_dt}")
        print(f"Formatted: {date_time_reported}")
    
    # Format incident datetime
    incident_datetime = ""
    if incident_date and incident_time:
        incident_datetime = f"{incident_date.strftime('%B %d, %Y')} at {incident_time.strftime('%I:%M %p')}"
    elif incident_date:
        incident_datetime = incident_date.strftime('%B %d, %Y')
    
    # Load template PDF and fill form fields
    template_path = os.path.join(settings.BASE_DIR, 'static', 'kp_forms', 'lupon_blotter_file.pdf')
    reader = PdfReader(template_path)
    writer = PdfWriter()
    
    # Fill form fields
    writer.append(reader)
    try:
        writer.update_page_form_field_values(
            writer.pages[0],
            {
                'brgy_blotter_case_number': str(report_id),
                'date_time': date_time_reported or '',
                'complainant_name': complainant_names or '',
                'complainant_addr': complainant_addresses or '',
                'complainant_contact_num': complainant_contacts or '',
                'respondent_name': respondent_names or '',
                'respondent_addr': respondent_addresses or '',
                'respondent_contact_num': respondent_contacts or '',
                'date_time_of_incident': incident_datetime,
                'incident_information': incident_desc or incident_subject or '',
                'complainant_printed_name': complainant_names or '',
                'brgy_captain': officials.get('BARANGAY CAPTAIN', ''),
                'brgy_sec': officials.get('BARANGAY SECRETARY', ''),
            }
        )
    except KeyError:
        # PDF form fields missing appearance dictionary - flatten and continue
        pass
    
    # Save to BytesIO
    output = BytesIO()
    writer.write(output)
    output.seek(0)
    
    # Create response
    response = HttpResponse(output.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="blotter_report_{report_id}_{datetime.now().strftime("%Y%m%d")}.pdf"'
    
    return response
