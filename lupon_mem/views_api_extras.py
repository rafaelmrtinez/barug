# Add these API endpoints to views_api.py for async data loading

@session_login_required
def case_detail_extras_api(request: HttpRequest, case_id: int):
    """Load non-critical case details asynchronously"""
    try:
        with connection.cursor() as cur:
            # Get KP-7 details, pangkat members, upcoming hearings in ONE query
            cur.execute("""
                WITH kp7 AS (
                    SELECT 
                        MAX(CASE WHEN LOWER(f.field_code) = 'complaint_details' THEN a.value_json #>> '{}' END) AS complaint,
                        MAX(CASE WHEN LOWER(f.field_code) = 'solutions_seeked' THEN a.value_json #>> '{}' END) AS solutions
                    FROM blotter_kp_submission s
                    JOIN kp_form kf ON kf.form_id = s.form_id
                    JOIN blotter_kp_answer a ON a.submission_id = s.submission_id
                    JOIN kp_field f ON f.field_id = a.field_id
                    WHERE s.blotter_case_id = %s AND UPPER(kf.form_code) = 'KP-7'
                      AND LOWER(f.field_code) IN ('complaint_details', 'solutions_seeked')
                ),
                pangkat AS (
                    SELECT ARRAY_AGG(DISTINCT a.value_json #>> '{}') as members
                    FROM blotter_kp_submission s
                    JOIN kp_form kf ON kf.form_id = s.form_id
                    JOIN blotter_kp_answer a ON a.submission_id = s.submission_id
                    JOIN kp_field f ON f.field_id = a.field_id
                    WHERE s.blotter_case_id = %s AND UPPER(kf.form_code) = 'KP-11'
                      AND LOWER(f.field_code) = 'pangkat_member_name' AND UPPER(s.status) = 'SUBMITTED'
                ),
                upcoming AS (
                    SELECT COUNT(*) as cnt
                    FROM blotter_kp_submission s
                    JOIN kp_form kf ON kf.form_id = s.form_id
                    JOIN blotter_kp_answer a ON a.submission_id = s.submission_id
                    JOIN kp_field f ON f.field_id = a.field_id
                    WHERE s.blotter_case_id = %s AND UPPER(kf.form_code) IN ('KP-8', 'KP-12')
                      AND LOWER(f.field_code) = 'hearing_date'
                      AND a.value_json #>> '{}' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                      AND TO_DATE(a.value_json #>> '{}', 'YYYY-MM-DD') >= CURRENT_DATE
                )
                SELECT 
                    (SELECT complaint FROM kp7),
                    (SELECT solutions FROM kp7),
                    (SELECT members FROM pangkat),
                    (SELECT cnt FROM upcoming)
            """, [case_id, case_id, case_id])
            
            row = cur.fetchone()
            
        return JsonResponse({
            'kp7_details': {
                'complaint_details': row[0],
                'solutions_seeked': row[1]
            },
            'pangkat_members': row[2] or [],
            'upcoming_hearings_count': row[3] or 0
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@session_login_required
def hearing_window_api(request: HttpRequest, case_id: int):
    """Get hearing window data asynchronously"""
    try:
        window = get_hearing_window(case_id)
        return JsonResponse(window or {})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
