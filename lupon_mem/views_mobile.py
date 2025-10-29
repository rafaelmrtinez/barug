# lupon_mem/views_mobile.py  (or wherever you keep mobile views)
from django.http import JsonResponse, HttpResponseBadRequest
from django.db import connection

def residents_search(request):
    if request.method != "GET":
        return HttpResponseBadRequest("Method not allowed")

    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        # keep responses quick if the query is too short
        return JsonResponse({"results": [], "page": 1, "limit": 0, "count": 0})

    # simple pagination
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except ValueError:
        page = 1
    try:
        limit = min(max(1, int(request.GET.get("limit", 20))), 50)  # cap to 50
    except ValueError:
        limit = 20
    offset = (page - 1) * limit

    like = f"%{q}%"

    # Fetch rows
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT
                p.person_id,
                trim(
                    coalesce(p.first_name,'') || ' ' ||
                    coalesce(p.middle_name,'') || ' ' ||
                    coalesce(p.last_name,'')  || ' ' ||
                    coalesce(p.suffix,'')
                ) AS full_name,

                coalesce(p.birthdate::text, '') AS birthdate
            FROM person p
            WHERE
                   p.first_name ILIKE %s
                OR p.last_name  ILIKE %s
                OR (p.first_name || ' ' || coalesce(p.middle_name,'') || ' ' || p.last_name) ILIKE %s
            ORDER BY p.last_name, p.first_name
            LIMIT %s OFFSET %s
            """,
            [like, like, like, limit, offset],
        )
        rows = cur.fetchall()

        # (optional) total count for pagination UI
        cur.execute(
            """
            SELECT count(*)
            FROM person p
            WHERE
                   p.first_name ILIKE %s
                OR p.last_name  ILIKE %s
                OR (p.first_name || ' ' || coalesce(p.middle_name,'') || ' ' || p.last_name) ILIKE %s
            """,
            [like, like, like],
        )
        total = cur.fetchone()[0]

    data = [
        {
            "id": r[0],
            "name": (r[1] or "").strip(),
        }
        for r in rows
    ]
    return JsonResponse({"results": data, "page": page, "limit": limit, "count": total})
