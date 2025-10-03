from django.db import connection

def exec_sql(sql, params=()):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        if cur.description:
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        return None

def exec_one(sql, params=()):
    rows = exec_sql(sql, params)
    return rows[0] if rows else None
