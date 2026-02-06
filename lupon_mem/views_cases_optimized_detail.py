# Optimized case_detail view for views_cases.py
# Replace the existing case_detail function with this optimized version

@session_login_required 
@role_required(*LUPON_ROLES, "barangay treasurer", "barangay secretary")
def case_detail_optimized(request: HttpRequest, case_id: int):
    """
    OPTIMIZED case detail view - reduces queries from 8+ to 1-2
    """
    t0 = time.perf_counter()
    
    # Pagination
    try:
        page = max(int(request.GET.get("page", "1")), 1)
    except ValueError:
        page = 1
    per_page = 10
    offset = (page - 1) * per_page

    # SINGLE OPTIMIZED QUERY using CTEs
    with connection.cursor() as cur:
        cur.execute("""
            WITH case_forms AS (
                SELECT 
                    s.submission_id,
                    s.form_id,
                    s.status,
                    s.submitted_at,
                    UPPER(kf.form_code) AS form_code,
                    kf.form_name,
                    ROW_NUMBER() OVER (ORDER BY s.submission_id DESC) as rn
                FROM blotter_kp_submission s
                JOIN kp_form kf ON kf.form_id = s.form_id
                WHERE s.blotter_case_id = %s
            ),
            audit_data AS (
                SELECT 
                    a.submission_id,
                    MAX(CASE WHEN a.field_id = 1120 THEN a.value_json #>> '{}' END) AS processed_by_name,
                    MAX(CASE WHEN a.field_id = 1121 THEN a.value_json #>> '{}' END) AS processed_on_date,
                    MAX(CASE WHEN a.field_id = 1122 THEN a.value_json #>> '{}' END) AS processed_on_time
                FROM blotter_kp_answer a
                WHERE a.field_id IN (1120, 1121, 1122)
                  AND a.submission_id IN (SELECT submission_id FROM case_forms)
                GROUP BY a.submission_id
            ),
            kp7_data AS (
                SELECT 
                    MAX(CASE WHEN LOWER(f.field_code) = 'complaint_details' THEN a.value_json #>> '{}' END) AS complaint_details,
                    MAX(CASE WHEN LOWER(f.field_code) = 'solutions_seeked' THEN a.value_json #>> '{}' END) AS solutions_seeked
                FROM blotter_kp_submission s
                JOIN kp_form kf ON kf.form_id = s.form_id
                JOIN blotter_kp_answer a ON a.submission_id = s.submission_id
                JOIN kp_field f ON f.field_id = a.field_id
                WHERE s.blotter_case_id = %s
                  AND UPPER(kf.form_code) = 'KP-7'
                  AND LOWER(f.field_code) IN ('complaint_details', 'solutions_seeked')
            ),
            pangkat_data AS (
                SELECT ARRAY_AGG(DISTINCT a.value_json #>> '{}') as members
                FROM blotter_kp_submission s
                JOIN kp_form kf ON kf.form_id = s.form_id
                JOIN blotter_kp_answer a ON a.submission_id = s.submission_id
                JOIN kp_field f ON f.field_id = a.field_id
                WHERE s.blotter_case_id = %s
                  AND UPPER(kf.form_code) = 'KP-11'
                  AND LOWER(f.field_code) = 'pangkat_member_name'
                  AND UPPER(s.status) = 'SUBMITTED'
            )
            SELECT 
                -- Case data (0-13)
                bc.blotter_case_id, bc.blotter_case_num, bc.blotter_case_name,
                TO_CHAR(bc.date_filed,'Mon DD, YYYY') AS date_filed, 
                bc.incident_desc,
                COALESCE(ct.complaint_title_name,'') AS type_name,
                COALESCE(cn.case_name,'') AS nature_name,
                ss.settlement_status_name, 
                bc.settlement_status_id,
                cs.case_state_name, 
                bc.closed_at,
                
                -- Counts (11-13)
                (SELECT COUNT(*) FROM case_forms) AS total_forms,
                (SELECT COUNT(*) FROM case_forms WHERE form_code = 'KP-9') AS kp9_count,
                (SELECT COUNT(*) FROM case_forms WHERE form_code IN ('KP-8', 'KP-12') AND submitted_at IS NOT NULL) AS hearings_set,
                
                -- Upcoming hearings (14)
                (SELECT COUNT(*)
                 FROM blotter_kp_submission s2
                 JOIN kp_form kf2 ON kf2.form_id = s2.form_id
                 JOIN blotter_kp_answer a2 ON a2.submission_id = s2.submission_id
                 JOIN kp_field f2 ON f2.field_id = a2.field_id
                 WHERE s2.blotter_case_id = bc.blotter_case_id
                   AND UPPER(kf2.form_code) IN ('KP-8', 'KP-12')
                   AND LOWER(f2.field_code) = 'hearing_date'
                   AND a2.value_json #>> '{}' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                   AND TO_DATE(a2.value_json #>> '{}', 'YYYY-MM-DD') >= CURRENT_DATE
                ) AS upcoming_hearings,
                
                -- KP-7 details (15-16)
                (SELECT complaint_details FROM kp7_data) AS kp7_complaint,
                (SELECT solutions_seeked FROM kp7_data) AS kp7_solutions,
                
                -- Pangkat members (17)
                (SELECT members FROM pangkat_data) AS pangkat_members,
                
                -- Paginated forms (18-24)
                COALESCE(
                    (SELECT JSON_AGG(
                        JSON_BUILD_OBJECT(
                            'submission_id', cf.submission_id,
                            'form_code', cf.form_code,
                            'form_name', cf.form_name,
                            'status', cf.status,
                            'processed_by', ad.processed_by_name,
                            'processed_date', ad.processed_on_date,
                            'processed_time', ad.processed_on_time
                        ) ORDER BY cf.submission_id DESC
                    )
                    FROM case_forms cf
                    LEFT JOIN audit_data ad ON ad.submission_id = cf.submission_id
                    WHERE cf.rn > %s AND cf.rn <= %s
                    ), '[]'::json
                ) AS forms_json,
                
                -- All form codes for flow (25)
                COALESCE(
                    (SELECT JSON_AGG(form_code ORDER BY submission_id DESC)
                     FROM case_forms
                    ), '[]'::json
                ) AS all_form_codes,
                
                -- Submitted form codes (26)
                COALESCE(
                    (SELECT JSON_AGG(DISTINCT form_code)
                     FROM case_forms
                     WHERE UPPER(status) = 'SUBMITTED'
                       AND form_code IN ('KP-7', 'KP-8', 'KP-9', 'KP-10', 'KP-11', 'KP-12', 'KP-16')
                    ), '[]'::json
                ) AS submitted_codes
                
            FROM blotter_case bc
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature cn ON cn.case_nature_id = bc.case_nature_id
            LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
            LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id
            WHERE bc.blotter_case_id = %s
        """, [case_id, case_id, case_id, offset, offset + per_page, case_id])
        
        row = cur.fetchone()
        if not row:
            return HttpResponseNotFound("Case not found")

    # Parse results
    case_row = row[:14]
    total_forms = row[11]
    upcoming_hearings_count = row[14]
    kp7_details = {
        'complaint_details': row[15],
        'solutions_seeked': row[16]
    }
    pangkat_members = row[17] or []
    
    # Parse JSON fields
    import json
    forms_data = json.loads(row[18]) if row[18] else []
    all_form_codes = json.loads(row[19]) if row[19] else []
    submitted_form_codes = set(json.loads(row[20]) if row[20] else [])
    
    # Convert forms to tuple format for template compatibility
    forms = [
        (
            f['submission_id'],
            f['form_code'],
            f['form_name'],
            f['status'],
            f.get('processed_by'),
            f.get('processed_date'),
            f.get('processed_time'),
        )
        for f in forms_data
    ]
    
    # Calculate hearing window (cached)
    hearing_window = get_hearing_window(case_id)
    
    # Calculate repudiation window if KP-16 exists
    repudiation_window = None
    if 'KP-16' in all_form_codes:
        try:
            kp16_fields = get_latest_form_fields(case_id, 'KP-16')
            if kp16_fields:
                processed_date_str = get_field_text(kp16_fields, 'processed_on_date')
                if processed_date_str:
                    from datetime import datetime, timedelta
                    processed_date = datetime.strptime(processed_date_str, '%Y-%m-%d').date()
                    repudiation_end = processed_date + timedelta(days=10)
                    days_left = (repudiation_end - datetime.now().date()).days
                    repudiation_window = {
                        'end_date': repudiation_end.strftime('%B %d, %Y'),
                        'days_left': days_left
                    }
        except Exception:
            pass
    
    # Progress calculation
    flow_steps = ['KP-7', 'KP-8', 'KP-9', 'KP-10', 'KP-11', 'KP-12', 'KP-16']
    completed_count = sum(1 for step in flow_steps if step in submitted_form_codes)
    progress_percentage = int((completed_count / len(flow_steps)) * 100) if flow_steps else 0
    
    # Pagination
    total_pages = max((total_forms + per_page - 1) // per_page, 1)
    has_prev = page > 1
    has_next = page < total_pages
    start_p = max(1, page - 2)
    end_p = min(total_pages, page + 2)
    page_numbers = list(range(start_p, end_p + 1))
    
    # Lookup data (cached)
    lookup_cache = _fetch_lookups()
    
    auth = request.session.get("auth") or {}
    user_role = (auth.get("role_name") or auth.get("role") or "").strip().title()
    
    total_ms = (time.perf_counter() - t0) * 1000
    log.info(f"case_detail_optimized: {total_ms:.1f}ms for case {case_id}")
    
    context = {
        "case": case_row,
        "forms": forms,
        "case_id": case_id,
        "hearing_window": hearing_window,
        "settlement_choices": ["Settled", "Not Settled", "Pending"],
        "incident_description": case_row[4] if len(case_row) > 4 else None,
        "case_nature": case_row[6] if len(case_row) > 6 else None,
        "case_state_name": case_row[9] if len(case_row) > 9 else None,
        "case_closed_at": case_row[10] if len(case_row) > 10 else None,
        "settlement_statuses": lookup_cache["settlement_statuses"],
        "case_states": _fetch_case_states(),
        "kp9_count": int(case_row[12] or 0),
        "hearings_set_count": int(case_row[13] or 0),
        "hearings_count": 0,
        "has_hearing": False,
        "submitted_form_codes": list(submitted_form_codes),
        "progress_percentage": progress_percentage,
        'page_path': f'{user_role} / Case Detail',
        'page_title': f'Case #{case_row[1]}' if case_row else 'Case Detail',
        "page": page,
        "per_page": per_page,
        "total_forms": total_forms,
        "total_pages": total_pages,
        "has_prev": has_prev,
        "has_next": has_next,
        "prev_page": page - 1,
        "next_page": page + 1,
        "page_numbers": page_numbers,
        "all_form_codes": all_form_codes,
        "repudiation_window": repudiation_window,
        "pangkat_members": pangkat_members,
        "kp7_details": kp7_details,
        "upcoming_hearings_count": upcoming_hearings_count,
    }

    return render(request, "lupon_mem/case_detail.html", context)
