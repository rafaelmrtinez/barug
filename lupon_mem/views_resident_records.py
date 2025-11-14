# lupon_mem/views_resident_records.py
from django.shortcuts import render, get_object_or_404
from django.http import HttpRequest, JsonResponse
from django.db import connection
from django.core.paginator import Paginator
from django.contrib import messages
from authentication.guards import session_login_required, role_required
from authentication.utils import nocache

LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}

@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
@nocache
def resident_records_list(request: HttpRequest):
    """
    Display a searchable list of residents with their blotter involvement summary.
    """
    search_query = request.GET.get('q', '').strip()
    page_number = request.GET.get('page', 1)
    
    with connection.cursor() as cur:
        # Get residents with their involvement counts
        if search_query:
            cur.execute("""
                SELECT 
                    p.person_id,
                    TRIM(COALESCE(p.first_name, '') || ' ' || COALESCE(p.middle_name, '') || ' ' || 
                         COALESCE(p.last_name, '') || ' ' || COALESCE(p.suffix, '')) AS full_name,
                    p.first_name,
                    p.last_name,
                    p.middle_name,
                    p.suffix,
                    -- Count reports as complainant
                    (SELECT COUNT(*) FROM complainant_report cr 
                     JOIN blotter_report br ON br.blotter_report_id = cr.blotter_report_id
                     WHERE cr.person_id = p.person_id) AS complainant_reports,
                    -- Count reports as respondent  
                    (SELECT COUNT(*) FROM respondent_report rr
                     JOIN blotter_report br ON br.blotter_report_id = rr.blotter_report_id
                     WHERE rr.person_id = p.person_id) AS respondent_reports,
                    -- Count cases as complainant
                    (SELECT COUNT(*) FROM complainant_case cc
                     JOIN blotter_case bc ON bc.blotter_case_id = cc.blotter_case_id
                     WHERE cc.person_id = p.person_id) AS complainant_cases,
                    -- Count cases as respondent
                    (SELECT COUNT(*) FROM respondent_case rc
                     JOIN blotter_case bc ON bc.blotter_case_id = rc.blotter_case_id
                     WHERE rc.person_id = p.person_id) AS respondent_cases,
                    -- Latest involvement date
                    GREATEST(
                        COALESCE((SELECT MAX(br.date_time_reported) FROM complainant_report cr 
                                 JOIN blotter_report br ON br.blotter_report_id = cr.blotter_report_id
                                 WHERE cr.person_id = p.person_id), '1900-01-01'::timestamp),
                        COALESCE((SELECT MAX(br.date_time_reported) FROM respondent_report rr
                                 JOIN blotter_report br ON br.blotter_report_id = rr.blotter_report_id
                                 WHERE rr.person_id = p.person_id), '1900-01-01'::timestamp),
                        COALESCE((SELECT MAX(bc.date_filed) FROM complainant_case cc
                                 JOIN blotter_case bc ON bc.blotter_case_id = cc.blotter_case_id
                                 WHERE cc.person_id = p.person_id), '1900-01-01'::date),
                        COALESCE((SELECT MAX(bc.date_filed) FROM respondent_case rc
                                 JOIN blotter_case bc ON bc.blotter_case_id = rc.blotter_case_id
                                 WHERE rc.person_id = p.person_id), '1900-01-01'::date)
                    ) AS latest_involvement
                FROM person p
                WHERE (p.first_name ILIKE %s OR p.last_name ILIKE %s OR 
                       p.middle_name ILIKE %s OR 
                       CONCAT(p.first_name, ' ', p.last_name) ILIKE %s)
                  AND (
                    EXISTS(SELECT 1 FROM complainant_report cr WHERE cr.person_id = p.person_id) OR
                    EXISTS(SELECT 1 FROM respondent_report rr WHERE rr.person_id = p.person_id) OR
                    EXISTS(SELECT 1 FROM complainant_case cc WHERE cc.person_id = p.person_id) OR
                    EXISTS(SELECT 1 FROM respondent_case rc WHERE rc.person_id = p.person_id)
                  )
                ORDER BY latest_involvement DESC NULLS LAST, p.last_name, p.first_name
                LIMIT 100
            """, [f'%{search_query}%'] * 4)
        else:
            cur.execute("""
                SELECT 
                    p.person_id,
                    TRIM(COALESCE(p.first_name, '') || ' ' || COALESCE(p.middle_name, '') || ' ' || 
                         COALESCE(p.last_name, '') || ' ' || COALESCE(p.suffix, '')) AS full_name,
                    p.first_name,
                    p.last_name,
                    p.middle_name,
                    p.suffix,
                    -- Count reports as complainant
                    (SELECT COUNT(*) FROM complainant_report cr 
                     JOIN blotter_report br ON br.blotter_report_id = cr.blotter_report_id
                     WHERE cr.person_id = p.person_id) AS complainant_reports,
                    -- Count reports as respondent  
                    (SELECT COUNT(*) FROM respondent_report rr
                     JOIN blotter_report br ON br.blotter_report_id = rr.blotter_report_id
                     WHERE rr.person_id = p.person_id) AS respondent_reports,
                    -- Count cases as complainant
                    (SELECT COUNT(*) FROM complainant_case cc
                     JOIN blotter_case bc ON bc.blotter_case_id = cc.blotter_case_id
                     WHERE cc.person_id = p.person_id) AS complainant_cases,
                    -- Count cases as respondent
                    (SELECT COUNT(*) FROM respondent_case rc
                     JOIN blotter_case bc ON bc.blotter_case_id = rc.blotter_case_id
                     WHERE rc.person_id = p.person_id) AS respondent_cases,
                    -- Latest involvement date
                    GREATEST(
                        COALESCE((SELECT MAX(br.date_time_reported) FROM complainant_report cr 
                                 JOIN blotter_report br ON br.blotter_report_id = cr.blotter_report_id
                                 WHERE cr.person_id = p.person_id), '1900-01-01'::timestamp),
                        COALESCE((SELECT MAX(br.date_time_reported) FROM respondent_report rr
                                 JOIN blotter_report br ON br.blotter_report_id = rr.blotter_report_id
                                 WHERE rr.person_id = p.person_id), '1900-01-01'::timestamp),
                        COALESCE((SELECT MAX(bc.date_filed) FROM complainant_case cc
                                 JOIN blotter_case bc ON bc.blotter_case_id = cc.blotter_case_id
                                 WHERE cc.person_id = p.person_id), '1900-01-01'::date),
                        COALESCE((SELECT MAX(bc.date_filed) FROM respondent_case rc
                                 JOIN blotter_case bc ON bc.blotter_case_id = rc.blotter_case_id
                                 WHERE rc.person_id = p.person_id), '1900-01-01'::date)
                    ) AS latest_involvement
                FROM person p
                WHERE EXISTS(SELECT 1 FROM complainant_report cr WHERE cr.person_id = p.person_id) OR
                      EXISTS(SELECT 1 FROM respondent_report rr WHERE rr.person_id = p.person_id) OR
                      EXISTS(SELECT 1 FROM complainant_case cc WHERE cc.person_id = p.person_id) OR
                      EXISTS(SELECT 1 FROM respondent_case rc WHERE rc.person_id = p.person_id)
                ORDER BY latest_involvement DESC NULLS LAST, p.last_name, p.first_name
                LIMIT 100
            """)
        
        residents = cur.fetchall()
    
    # Paginate results
    paginator = Paginator(residents, 20)
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'lupon_mem/resident_records_list.html', {
        'page_obj': page_obj,
        'residents': page_obj.object_list,
        'search_query': search_query,
        'page_title': 'Resident Records',
    })


@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
@nocache
def resident_records_detail(request: HttpRequest, person_id: int):
    """
    Display detailed blotter report and case history for a specific resident.
    """
    with connection.cursor() as cur:
        # Get person details
        cur.execute("""
            SELECT person_id, first_name, last_name, middle_name, suffix,
                   TRIM(COALESCE(first_name, '') || ' ' || COALESCE(middle_name, '') || ' ' || 
                        COALESCE(last_name, '') || ' ' || COALESCE(suffix, '')) AS full_name
            FROM person 
            WHERE person_id = %s
        """, [person_id])
        
        person_row = cur.fetchone()
        if not person_row:
            messages.error(request, "Person not found.")
            return render(request, 'lupon_mem/resident_records_detail.html', {
                'person': None,
                'report_history': [],
                'case_history': [],
                'page_title': 'Resident Not Found',
            })
        
        person = {
            'person_id': person_row[0],
            'first_name': person_row[1] or '',
            'last_name': person_row[2] or '',
            'middle_name': person_row[3] or '',
            'suffix': person_row[4] or '',
            'full_name': person_row[5],
        }
        
        # Get blotter report history using the database function
        cur.execute("SELECT * FROM fn_person_blotter_report_history(%s)", [person_id])
        report_columns = [desc[0] for desc in cur.description]
        report_rows = cur.fetchall()
        
        report_history = []
        for row in report_rows:
            report_dict = dict(zip(report_columns, row))
            report_history.append(report_dict)
        
        # Get case history using the database function
        cur.execute("SELECT * FROM fn_person_blotter_case_history(%s)", [person_id])
        case_columns = [desc[0] for desc in cur.description]
        case_rows = cur.fetchall()
        
        case_history = []
        for row in case_rows:
            case_dict = dict(zip(case_columns, row))
            case_history.append(case_dict)
    
    # Calculate summary counts
    complainant_reports_count = sum(1 for r in report_history if r.get('role_in_report') == 'COMPLAINANT')
    respondent_reports_count = sum(1 for r in report_history if r.get('role_in_report') == 'RESPONDENT')
    complainant_cases_count = sum(1 for c in case_history if c.get('role_in_case') == 'COMPLAINANT')
    respondent_cases_count = sum(1 for c in case_history if c.get('role_in_case') == 'RESPONDENT')
    
    return render(request, 'lupon_mem/resident_records_detail.html', {
        'person': person,
        'report_history': report_history,
        'case_history': case_history,
        'complainant_reports_count': complainant_reports_count,
        'respondent_reports_count': respondent_reports_count,
        'complainant_cases_count': complainant_cases_count,
        'respondent_cases_count': respondent_cases_count,
        'page_title': f'Records for {person["full_name"]}',
    })


@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def resident_records_api(request: HttpRequest):
    """
    API endpoint for searching residents (for autocomplete/AJAX).
    """
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'results': []})
    
    with connection.cursor() as cur:
        cur.execute("""
            SELECT 
                p.person_id,
                TRIM(COALESCE(p.first_name, '') || ' ' || COALESCE(p.middle_name, '') || ' ' || 
                     COALESCE(p.last_name, '') || ' ' || COALESCE(p.suffix, '')) AS full_name,
                -- Total involvement count
                (SELECT COUNT(*) FROM complainant_report cr WHERE cr.person_id = p.person_id) +
                (SELECT COUNT(*) FROM respondent_report rr WHERE rr.person_id = p.person_id) +
                (SELECT COUNT(*) FROM complainant_case cc WHERE cc.person_id = p.person_id) +
                (SELECT COUNT(*) FROM respondent_case rc WHERE rc.person_id = p.person_id) AS total_involvement
            FROM person p
            WHERE (p.first_name ILIKE %s OR p.last_name ILIKE %s OR 
                   p.middle_name ILIKE %s OR 
                   CONCAT(p.first_name, ' ', p.last_name) ILIKE %s)
              AND (
                EXISTS(SELECT 1 FROM complainant_report cr WHERE cr.person_id = p.person_id) OR
                EXISTS(SELECT 1 FROM respondent_report rr WHERE rr.person_id = p.person_id) OR
                EXISTS(SELECT 1 FROM complainant_case cc WHERE cc.person_id = p.person_id) OR
                EXISTS(SELECT 1 FROM respondent_case rc WHERE rc.person_id = p.person_id)
              )
            ORDER BY total_involvement DESC, p.last_name, p.first_name
            LIMIT 20
        """, [f'%{query}%'] * 4)
        
        results = []
        for row in cur.fetchall():
            results.append({
                'id': row[0],
                'name': row[1],
                'involvement_count': row[2]
            })
    
    return JsonResponse({'results': results})