@session_login_required 
@role_required(*LUPON_ROLES, "barangay treasurer")
def case_detail(request: HttpRequest, case_id: int):
    # Ultra-fast single query with minimal processing
    with connection.cursor() as cur:
        cur.execute("""
            SELECT 
                bc.blotter_case_id, bc.blotter_case_num, bc.blotter_case_name,
                TO_CHAR(bc.date_filed,'Mon DD, YYYY') AS date_filed, bc.incident_desc,
                COALESCE(ct.complaint_title_name,'—') AS type_name,
                COALESCE(cn.case_name,'—') AS nature_name,
                ss.settlement_status_name, bc.settlement_status_id,
                cs.case_state_name, bc.closed_at,
                -- Forms count
                (SELECT COUNT(*) FROM blotter_kp_submission s2 WHERE s2.blotter_case_id = bc.blotter_case_id) as forms_count,
                -- KP9 stats
                (SELECT COUNT(*) FROM blotter_kp_submission s3 
                 JOIN kp_form kf3 ON kf3.form_id = s3.form_id 
                 WHERE s3.blotter_case_id = bc.blotter_case_id AND UPPER(kf3.form_code) = 'KP-9') as kp9_count,
                -- Hearings set
                (SELECT COUNT(*) FROM blotter_kp_submission s4 
                 JOIN kp_form kf4 ON kf4.form_id = s4.form_id 
                 WHERE s4.blotter_case_id = bc.blotter_case_id 
                 AND UPPER(kf4.form_code) IN ('KP-8', 'KP-12') 
                 AND s4.submitted_at IS NOT NULL) as hearings_set
            FROM blotter_case bc
            LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
            LEFT JOIN case_nature cn ON cn.case_nature_id = bc.case_nature_id
            LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
            LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id
            WHERE bc.blotter_case_id = %s
        """, [case_id])
        
        case_row = cur.fetchone()
        if not case_row:
            return HttpResponseNotFound("Case not found")
        
        # Get forms - only essential data
        cur.execute("""
            SELECT s.submission_id, UPPER(kf.form_code), kf.form_name, s.status,
                   CASE WHEN s.submitted_at IS NULL THEN '—'
                        ELSE TO_CHAR(s.submitted_at,'Mon DD HH12:MI AM') END
            FROM blotter_kp_submission s
            JOIN kp_form kf ON kf.form_id = s.form_id
            WHERE s.blotter_case_id = %s
            ORDER BY s.submitted_at DESC NULLS LAST
            LIMIT 20
        """, [case_id])
        forms = cur.fetchall()
    
    # Minimal context - only what's absolutely needed
    context = {
        "case": case_row[:11],
        "forms": [(f[0], f[1], f[2], f[3], f[4], None, None, None) for f in forms],
        "case_id": case_id,
        "settlement_choices": ["Settled", "Not Settled", "Pending"],
        "hearing_gate": {"hearings_set": case_row[14]},
        "incident_description": case_row[4],
        "case_nature": case_row[6],
        "case_state_name": case_row[9],
        "case_closed_at": case_row[10],
        "kp9_count": case_row[12],
        "hearings_set_count": case_row[14],
        "hearings_count": 0,
        "kp9_latest_status": None,
        "kp9_latest_party": None,
        "kp9_pending_count": 0,
        "has_hearing": case_row[14] > 0,
        "force_open_block_modal": False,
        "block_reason": None,
        "block_due_to_summons": False,
        "block_due_to_hearing": False,
        "block_reason_summons": "",
        "block_reason_hearing": "",
        "has_med_summary": False,
        "med_summary_sid": None,
    }
    
    return render(request, "lupon_mem/case_detail.html", context)