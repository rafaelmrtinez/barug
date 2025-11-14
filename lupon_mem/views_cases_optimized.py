# Optimized case_detail view for fastest loading
@session_login_required 
@role_required(*LUPON_ROLES, "barangay treasurer")
def case_detail(request: HttpRequest, case_id: int):
    t0 = time.perf_counter()
    
    # Single optimized query for all case data
    with connection.cursor() as cur:
        cur.execute("""
            WITH case_data AS (
                SELECT
                    bc.blotter_case_id,
                    bc.blotter_case_num,
                    bc.blotter_case_name,
                    TO_CHAR(bc.date_filed,'Mon DD, YYYY') AS date_filed,
                    bc.incident_desc,
                    COALESCE(ct.complaint_title_name,'—') AS type_name,
                    COALESCE(cn.case_name,'—') AS nature_name,
                    ss.settlement_status_name,
                    bc.settlement_status_id,
                    cs.case_state_name,
                    bc.closed_at
                FROM blotter_case bc
                LEFT JOIN complaint_title ct ON ct.complaint_title_id = bc.complaint_title_id
                LEFT JOIN case_nature cn ON cn.case_nature_id = bc.case_nature_id
                LEFT JOIN settlement_status ss ON ss.settlement_status_id = bc.settlement_status_id
                LEFT JOIN case_state cs ON cs.case_state_id = bc.case_state_id
                WHERE bc.blotter_case_id = %s
            ),
            forms_data AS (
                SELECT
                    s.submission_id,
                    UPPER(kf.form_code) AS form_code,
                    kf.form_name,
                    s.status,
                    CASE WHEN s.submitted_at IS NULL THEN '—'
                         ELSE TO_CHAR(s.submitted_at,'Mon DD, YYYY HH12:MI AM')
                    END AS submitted_fmt,
                    ppt.party_name AS kp17_party,
                    TRIM(COALESCE(p.last_name,'') || ', ' || COALESCE(p.first_name,'') || ' ' || COALESCE(p.middle_name,'')) AS kp17_person,
                    s.submitted_at
                FROM blotter_kp_submission s
                JOIN kp_form kf ON kf.form_id = s.form_id
                LEFT JOIN kp17_repudiation m ON m.submission_id = s.submission_id
                LEFT JOIN kp_party_type ppt ON ppt.kp_party_type_id = m.party_type_id
                LEFT JOIN person p ON p.person_id = m.party_person_id
                WHERE s.blotter_case_id = %s
            ),
            kp9_stats AS (
                SELECT
                    COUNT(*) as kp9_count,
                    COUNT(*) FILTER (WHERE a.submission_id IS NULL) as kp9_pending_count,
                    (SELECT a2.status FROM kp9_attendance a2 
                     JOIN blotter_kp_submission s2 ON s2.submission_id = a2.submission_id
                     WHERE s2.blotter_case_id = %s
                     ORDER BY a2.marked_at DESC NULLS LAST LIMIT 1) as latest_status,
                    (SELECT a2.no_show_party FROM kp9_attendance a2 
                     JOIN blotter_kp_submission s2 ON s2.submission_id = a2.submission_id
                     WHERE s2.blotter_case_id = %s
                     ORDER BY a2.marked_at DESC NULLS LAST LIMIT 1) as latest_party
                FROM blotter_kp_submission s
                JOIN kp_form kf ON kf.form_id = s.form_id AND UPPER(kf.form_code) = 'KP-9'
                LEFT JOIN kp9_attendance a ON a.submission_id = s.submission_id
                WHERE s.blotter_case_id = %s
            ),
            hearing_stats AS (
                SELECT 
                    COUNT(*) FILTER (WHERE s.submitted_at IS NOT NULL) as hearings_set,
                    MAX(s.submitted_at) as latest_notice_submitted_at
                FROM blotter_kp_submission s
                JOIN kp_form kf ON kf.form_id = s.form_id
                WHERE s.blotter_case_id = %s AND UPPER(kf.form_code) IN ('KP-8', 'KP-12')
            )
            SELECT 
                cd.*,
                fd.submission_id, fd.form_code, fd.form_name, fd.status, fd.submitted_fmt, 
                fd.kp17_party, fd.kp17_person, fd.submitted_at,
                ks.kp9_count, ks.kp9_pending_count, ks.latest_status, ks.latest_party,
                hs.hearings_set, hs.latest_notice_submitted_at
            FROM case_data cd
            CROSS JOIN kp9_stats ks
            CROSS JOIN hearing_stats hs
            LEFT JOIN forms_data fd ON TRUE
            ORDER BY (fd.submitted_at IS NULL), fd.submitted_at DESC, fd.submission_id DESC
        """, [case_id, case_id, case_id, case_id, case_id, case_id])
        
        rows = cur.fetchall()
        
        if not rows:
            return HttpResponseNotFound("Case not found")
        
        # Extract case data from first row
        first_row = rows[0]
        case = first_row[:11]  # First 11 columns are case data
        case_state_name = first_row[9]
        case_closed_at = first_row[10]
        
        # Extract stats
        kp9_count = first_row[18] or 0
        kp9_pending_count = first_row[19] or 0
        kp9_latest_status = (first_row[20] or "").upper() if first_row[20] else None
        kp9_latest_party = (first_row[21] or "").upper() if first_row[21] else None
        hearings_set_count = first_row[22] or 0
        latest_notice_dt = first_row[23]
        
        # Extract forms data
        forms_raw = []
        for row in rows:
            if row[11]:  # submission_id exists
                forms_raw.append(row[11:18])  # Form columns
        
        # Cache settlement choices
        cache_key = "settlement_choices_v1"
        settlement_choices = cache.get(cache_key)
        if not settlement_choices:
            cur.execute("SELECT settlement_status_name FROM settlement_status ORDER BY settlement_status_name")
            settlement_choices = [r[0] for r in cur.fetchall()]
            cache.set(cache_key, settlement_choices, 600)
    
    # Minimal sequence labeling (only if forms exist)
    forms = forms_raw
    if forms_raw:
        def _ordinal(n: int) -> str:
            n = int(n)
            if 11 <= (n % 100) <= 13:
                suffix = "th"
            else:
                suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
            return f"{n}{suffix}"
        
        # Simple sequence labels
        form_seq_labels = {}
        counters = {"KP-9": 0, "MED-ATT-2025": 0, "KP-8": 0, "KP-12": 0}
        
        for form_data in sorted(forms_raw, key=lambda x: x[7] or '1900-01-01'):  # Sort by submitted_at
            sid, code = int(form_data[0]), form_data[1]
            if code in counters:
                counters[code] += 1
                n = counters[code]
                if code == "KP-9":
                    form_seq_labels[sid] = f"{_ordinal(n)} Summons"
                elif code == "MED-ATT-2025":
                    form_seq_labels[sid] = f"{_ordinal(n)} Med Attendance"
                elif code in ("KP-8", "KP-12"):
                    form_seq_labels[sid] = f"{_ordinal(n)} Hearing"
        
        forms = [(*row, form_seq_labels.get(int(row[0]))) for row in forms_raw]
    
    # Minimal gate logic
    def _fmt_dt(dt) -> str | None:
        if not dt:
            return None
        try:
            from django.utils import timezone
            return timezone.localtime(dt).strftime("%b %d, %Y %I:%M %p")
        except Exception:
            return None
    
    latest_hearing_dt = _fmt_dt(latest_notice_dt)
    
    # Simple blocking logic
    block_due_to_summons = kp9_pending_count > 0
    block_reason_summons = f"{kp9_pending_count} summons pending attendance marking." if block_due_to_summons else ""
    
    # Check for MED summary
    has_med_summary = any(f[1] in ["MED1-SETTLED", "MED2-SETTLED", "MED3-SETTLED"] for f in forms_raw)
    med_summary_sid = next((int(f[0]) for f in forms_raw if f[1] in ["MED1-SETTLED", "MED2-SETTLED", "MED3-SETTLED"]), None)
    
    total_ms = (time.perf_counter() - t0) * 1000
    log.info(f"case_detail optimized: {total_ms:.1f}ms")
    
    context = {
        "case": case,
        "forms": forms,
        "case_id": case_id,
        "settlement_choices": settlement_choices,
        "hearing_gate": {"hearings_set": hearings_set_count, "latest_notice_submitted_at": latest_notice_dt},
        
        "incident_description": case[4] if case else None,
        "case_nature": case[6] if case else None,
        "case_state_name": case_state_name,
        "case_closed_at": case_closed_at,
        
        # KPIs
        "latest_hearing_dt": latest_hearing_dt,
        "last_hearing_dt": latest_hearing_dt,
        "kp9_count": kp9_count,
        "hearings_set_count": hearings_set_count,
        "hearings_count": 0,  # Simplified
        
        # KP-9 state
        "kp9_latest_status": kp9_latest_status,
        "kp9_latest_party": kp9_latest_party,
        "kp9_pending_count": kp9_pending_count,
        "has_hearing": hearings_set_count > 0,
        
        # Blocking
        "force_open_block_modal": bool(request.GET.get("open_block_modal")),
        "block_reason": request.GET.get("reason"),
        "block_due_to_summons": block_due_to_summons,
        "block_due_to_hearing": False,  # Simplified
        "block_reason_summons": block_reason_summons,
        "block_reason_hearing": "",
        
        # Summary
        "has_med_summary": has_med_summary,
        "med_summary_sid": med_summary_sid,
        "load_time_ms": f"{total_ms:.1f}",
    }
    
    return render(request, "lupon_mem/case_detail.html", context)