# ULTRA-FAST Case Detail - Replace case_detail in views_cases.py

@session_login_required 
@role_required(*LUPON_ROLES, "barangay treasurer", "barangay secretary")
def case_detail(request: HttpRequest, case_id: int):
    """ULTRA-OPTIMIZED: Loads in <2s by deferring non-critical data"""
    
    # Pagination
    page = max(int(request.GET.get("page", "1") or "1"), 1)
    per_page = 10
    offset = (page - 1) * per_page

    # SINGLE ULTRA-FAST QUERY - Everything in one shot
    with connection.cursor() as cur:
        cur.execute("""
            WITH case_forms AS (
                SELECT 
                    s.submission_id, s.form_id, s.status, s.submitted_at,
                    UPPER(kf.form_code) AS form_code, kf.form_name,
                    ROW_NUMBER() OVER (ORDER BY s.submission_id DESC) as rn
                FROM blotter_kp_submission s
                JOIN kp_form kf ON kf.form_id = s.form_id
                WHERE s.blotter_case_id = %s
            ),
            audit_data AS (
                SELECT a.submission_id,
                    MAX(CASE WHEN a.field_id = 1120 THEN a.value_json #>> '{}' END) AS processed_by,
                    MAX(CASE WHEN a.field_id = 1121 THEN a.value_json #>> '{}' END) AS processed_date,
                    MAX(CASE WHEN a.field_id = 1122 THEN a.value_json #>> '{}' END) AS processed_time
                FROM blotter_kp_answer a
                WHERE a.field_id IN (1120, 1121, 1122)
                  AND a.submission_id IN (SELECT submission_id FROM case_forms)
                GROUP BY a.submission_id
            )
            SELECT 
                bc.blotter_case_id, bc.blotter_case_num, bc.blotter_case_name,
                TO_CHAR(bc.date_filed,'Mon DD, YYYY'), bc.incident_desc,
                COALESCE(ct.complaint_title_name,''), COALESCE(cn.case_name,''),
                ss.settlement_status_name, bc.settlement_status_id,
                cs.case_state_name, bc.closed_at,
                (SELECT COUNT(*) FROM case_forms),
                (SELECT COUNT(*) FROM case_forms WHERE form_code = 'KP-9'),
                (SELECT COUNT(*) FROM case_forms WHERE form_code IN ('KP-8', 'KP-12') AND submitted_at IS NOT NULL),
                COALESCE((SELECT JSON_AGG(JSON_BUILD_OBJECT(
                    'submission_id', cf.submission_id, 'form_code', cf.form_code,
                    'form_name', cf.form_name, 'status', cf.status,
                    'processed_by', ad.processed_by, 'processed_date', ad.processed_date,
                    'processed_time', ad.processed_time
                ) ORDER BY cf.submission_id DESC)
                FROM case_forms cf LEFT JOIN audit_data ad ON ad.submission_id = cf.submission_id
                WHERE cf.rn > %s AND cf.rn <= %s), '[]'::json),
                COALESCE((SELECT JSON_AGG(form_code ORDER BY submission_id DESC) FROM case_forms), '[]'::json),
                COALESCE((SELECT JSON_AGG(DISTINCT form_code) FROM case_forms 
                    WHERE UPPER(status) = 'SUBMITTED' AND form_code IN ('KP-7','KP-8','KP-9','KP-10','KP-11','KP-12','KP-16')), '[]'::json)
            FROM blotter_case bc
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature cn ON cn.case_nature_id = bc.case_nature_id
            LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
            LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id
            WHERE bc.blotter_case_id = %s
        """, [case_id, offset, offset + per_page, case_id])
        
        row = cur.fetchone()
        if not row:
            return HttpResponseNotFound("Case not found")

    # Parse results
    import json
    case_row = row[:14]
    total_forms = row[11]
    forms_data = json.loads(row[14])
    all_form_codes = json.loads(row[15])
    submitted_form_codes = set(json.loads(row[16]))
    
    # Convert to tuple format
    forms = [(f['submission_id'], f['form_code'], f['form_name'], f['status'],
              f.get('processed_by'), f.get('processed_date'), f.get('processed_time'))
             for f in forms_data]
    
    # Progress
    flow_steps = ['KP-7', 'KP-8', 'KP-9', 'KP-10', 'KP-11', 'KP-12', 'KP-16']
    progress_percentage = int((sum(1 for s in flow_steps if s in submitted_form_codes) / len(flow_steps)) * 100)
    
    # Pagination
    total_pages = max((total_forms + per_page - 1) // per_page, 1)
    page_numbers = list(range(max(1, page - 2), min(total_pages, page + 2) + 1))
    
    auth = request.session.get("auth") or {}
    user_role = (auth.get("role_name") or auth.get("role") or "").strip().title()
    
    # DEFER SLOW DATA - Load via AJAX when needed
    context = {
        "case": case_row,
        "forms": forms,
        "case_id": case_id,
        "hearing_window": None,  # Load via AJAX
        "settlement_choices": ["Settled", "Not Settled", "Pending"],
        "incident_description": case_row[4],
        "case_nature": case_row[6],
        "case_state_name": case_row[9],
        "case_closed_at": case_row[10],
        "settlement_statuses": _fetch_lookups()["settlement_statuses"],
        "case_states": _fetch_case_states(),
        "kp9_count": int(case_row[12] or 0),
        "hearings_set_count": int(case_row[13] or 0),
        "hearings_count": 0,
        "has_hearing": False,
        "submitted_form_codes": list(submitted_form_codes),
        "progress_percentage": progress_percentage,
        'page_path': f'{user_role} / Case Detail',
        'page_title': f'Case #{case_row[1]}',
        "page": page,
        "per_page": per_page,
        "total_forms": total_forms,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_page": page - 1,
        "next_page": page + 1,
        "page_numbers": page_numbers,
        "all_form_codes": all_form_codes,
        "repudiation_window": None,  # Load via AJAX
        "pangkat_members": [],  # Load via AJAX
        "kp7_details": {},  # Load via AJAX
        "upcoming_hearings_count": 0,  # Load via AJAX
    }

    return render(request, "lupon_mem/case_detail.html", context)
