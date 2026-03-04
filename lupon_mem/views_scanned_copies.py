from django.shortcuts import render
from django.http import HttpRequest, HttpResponse
from django.db import connection
from authentication.guards import session_login_required, role_required

LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}

@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer", "barangay secretary")
def view_scanned_copies(request: HttpRequest, case_id: int):
    """View all scanned copies for a case"""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT bc.blotter_case_num, bc.blotter_case_name
            FROM blotter_case bc
            WHERE bc.blotter_case_id = %s
        """, [case_id])
        case_row = cur.fetchone()
        
        cur.execute("""
            SELECT file_name, document_type, uploaded_at, file_path, case_document_id
            FROM case_document
            WHERE blotter_case_id = %s AND is_deleted = FALSE
            ORDER BY uploaded_at DESC
        """, [case_id])
        documents = cur.fetchall()
    
    auth = request.session.get("auth") or {}
    user_role = (auth.get("role_name") or auth.get("role") or "").strip().title()
    
    return render(request, "lupon_mem/scanned_copies.html", {
        "case_id": case_id,
        "case_num": case_row[0] if case_row else "",
        "case_name": case_row[1] if case_row else "",
        "documents": documents,
        "page_path": f"{user_role} / Scanned Copies",
        "page_title": f"Scanned Copies - Case #{case_row[0] if case_row else case_id}"
    })
