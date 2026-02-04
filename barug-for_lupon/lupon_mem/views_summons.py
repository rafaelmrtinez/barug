# lupon_mem/views_summons.py
from __future__ import annotations
from typing import List
from django.http import JsonResponse, HttpRequest
from django.db import connection
from authentication.guards import session_login_required, role_required
from .views_shared import LUPON_ROLES, _get_person_mobile_number

@session_login_required
@role_required(*LUPON_ROLES)
def staff_lookup(request: HttpRequest):
    sid_raw = (request.GET.get("staff_id") or "").strip()
    if not sid_raw.isdigit():
        return JsonResponse({"ok": False, "error": "Invalid staff_id."}, status=400)
    staff_id = int(sid_raw)
    with connection.cursor() as cur:
        cur.execute("""
            SELECT
              s.staff_id,
              p.person_id,
              trim(coalesce(p.first_name,'') || ' ' ||
                   coalesce(p.middle_name,'') || ' ' ||
                   coalesce(p.last_name,'')  || ' ' ||
                   coalesce(p.suffix,''))    AS name,
              coalesce(r.role_name,'')       AS role
            FROM staff s
            JOIN person p ON p.person_id = s.person_id
            LEFT JOIN rolee r ON r.role_id = s.role_id
            WHERE s.staff_id=%s
            LIMIT 1
        """, [staff_id])
        row = cur.fetchone()
    if not row:
        return JsonResponse({"ok": False, "error": "Staff not found."}, status=404)
    _staff_id, person_id, name, role = row
    mobile = _get_person_mobile_number(person_id) or ""
    return JsonResponse({"ok": True, "result": {
        "id": _staff_id, "person_id": person_id,
        "name": (name or "").strip(), "role": (role or "").strip(),
        "mobile": mobile.strip()
    }})

@session_login_required
@role_required(*LUPON_ROLES)
def staff_suggest(request: HttpRequest):
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})
    like = f"%{q}%"
    with connection.cursor() as cur:
        cur.execute("""
            SELECT s.staff_id,
                   trim(
                       coalesce(p.first_name,'') || ' ' ||
                       coalesce(p.middle_name,'') || ' ' ||
                       coalesce(p.last_name,'') || ' ' ||
                       coalesce(p.suffix,'')
                   ) AS name
            FROM staff s
            JOIN person p ON p.person_id = s.person_id
            JOIN rolee  r ON r.role_id = s.role_id
            WHERE (r.role_name IN ('BARANGAY LUPON MEMBER','BARANGAY LUPON PRESIDENT'))
              AND (
                   p.first_name ILIKE %s
                OR p.last_name  ILIKE %s
                OR (p.first_name || ' ' || p.last_name) ILIKE %s
              )
            ORDER BY name
            LIMIT 20
        """, [like, like, like])
        rows = cur.fetchall()
    return JsonResponse({"results": [{"id": r[0], "name": r[1].strip()} for r in rows]})

@session_login_required
@role_required(*LUPON_ROLES)
def staff_suggest_all(request: HttpRequest):
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})
    like = f"%{q}%"
    with connection.cursor() as cur:
        cur.execute("""
            SELECT s.staff_id,
                   trim(
                       coalesce(p.first_name,'') || ' ' ||
                       coalesce(p.middle_name,'') || ' ' ||
                       coalesce(p.last_name,'') || ' ' ||
                       coalesce(p.suffix,'')
                   ) AS name
            FROM staff s
            JOIN person p ON p.person_id = s.person_id
            JOIN rolee  r ON r.role_id = s.role_id
            WHERE r.role_name IN (
                'BARANGAY LUPON MEMBER',
                'BARANGAY LUPON PRESIDENT',
                'BARANGAY SECRETARY',
                'BARANGAY CAPTAIN'
            )
              AND (
                   p.first_name ILIKE %s
                OR p.last_name  ILIKE %s
                OR (p.first_name || ' ' || p.last_name) ILIKE %s
              )
            ORDER BY name
            LIMIT 20
        """, [like, like, like])
        rows = cur.fetchall()
    return JsonResponse({"results": [{"id": r[0], "name": r[1].strip()} for r in rows]})

@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def person_suggest(request: HttpRequest):
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})
    like = f"%{q}%"
    with connection.cursor() as cur:
        cur.execute("""
            SELECT p.person_id,
                   trim(
                       coalesce(p.first_name,'') || ' ' ||
                       coalesce(p.middle_name,'') || ' ' ||
                       coalesce(p.last_name,'')  || ' ' ||
                       coalesce(p.suffix,'')
                   ) AS name
            FROM person p
            WHERE p.first_name ILIKE %s
               OR p.last_name  ILIKE %s
               OR (p.first_name || ' ' || p.last_name) ILIKE %s
            ORDER BY name
            LIMIT 20
        """, [like, like, like])
        rows = cur.fetchall()
    return JsonResponse({"results": [{"id": r[0], "name": r[1].strip()} for r in rows]})
