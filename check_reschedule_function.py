import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'barug.settings')
django.setup()

from django.db import connection

# First, let's see the current function
with connection.cursor() as cur:
    cur.execute("""
        SELECT pg_get_functiondef(oid) 
        FROM pg_proc 
        WHERE proname = 'fn_reschedule_hearing'
    """)
    result = cur.fetchone()
    if result:
        print("Current function definition:")
        print(result[0])
    else:
        print("Function not found")
