"""
Debug script to check KP-8 data in the database
Run this with: python manage.py shell < debug_kp8_data.py
"""
from django.db import connection

# Check specific submissions
submission_ids = [186, 187, 188, 191, 192, 193, 196, 197, 198]

print("\n=== CHECKING SUBMISSION DATA ===\n")
with connection.cursor() as cur:
    for sid in submission_ids:
        cur.execute("""
            SELECT s.submission_id, s.blotter_case_id, f.form_code, f.form_name
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            WHERE s.submission_id = %s
        """, [sid])
        row = cur.fetchone()
        if row:
            print(f"Submission {sid}: Case={row[1]}, Form={row[2]} ({row[3]})")
            
            # Get answers for this submission
            cur.execute("""
                SELECT fld.field_code, fld.base_label, a.value_json
                FROM blotter_kp_answer a
                JOIN kp_field fld ON fld.field_id = a.field_id
                WHERE a.submission_id = %s
                ORDER BY fld.field_code
            """, [sid])
            answers = cur.fetchall()
            for field_code, label, value in answers:
                if field_code in ('date_notified', 'hearing_time', 'curr_date', 'offcr_ret_date'):
                    print(f"  {field_code}: {value}")
            print()

# Now check what fetch_case_kp8_data would return for a specific case
print("\n=== CHECKING KP-8 DATA FOR CASE ===\n")
with connection.cursor() as cur:
    # Get case_id from first submission
    cur.execute("SELECT blotter_case_id FROM blotter_kp_submission WHERE submission_id = %s", [186])
    row = cur.fetchone()
    if row:
        case_id = row[0]
        print(f"Case ID: {case_id}\n")
        
        # Run the same query as fetch_case_kp8_data
        cur.execute("""
            SELECT s.submission_id, a.value_json, fld.field_code 
            FROM blotter_kp_submission s
            JOIN kp_form f ON f.form_id = s.form_id
            JOIN blotter_kp_answer a ON a.submission_id = s.submission_id
            JOIN kp_field fld ON fld.field_id = a.field_id
            WHERE s.blotter_case_id = %s AND UPPER(f.form_code) = 'KP-8'
            AND fld.field_code IN ('date_notified', 'hearing_time')
            ORDER BY s.submission_id, fld.field_code
        """, [case_id])
        
        print("KP-8 Query Results:")
        for sid, val, fcode in cur.fetchall():
            print(f"  Submission {sid}, {fcode}: {val}")
