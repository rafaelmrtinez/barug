import os
import sys
import django
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'barug.settings')
django.setup()

from django.db import connection

print("=" * 60)
print("CASE DETAIL PERFORMANCE DIAGNOSTIC")
print("=" * 60)

# Check 1: Indexes
print("\n1. Checking indexes on blotter_kp_submission...")
with connection.cursor() as cur:
    cur.execute("""
        SELECT indexname 
        FROM pg_indexes 
        WHERE tablename = 'blotter_kp_submission' 
        AND indexname LIKE 'idx_%'
    """)
    indexes = [r[0] for r in cur.fetchall()]
    if indexes:
        print(f"   [OK] Found {len(indexes)} custom indexes:")
        for idx in indexes:
            print(f"     - {idx}")
    else:
        print("   [ERROR] NO CUSTOM INDEXES FOUND!")
        print("   -> Run: psql -f sql\\case_detail_performance_indexes.sql")

# Check 2: Query performance
print("\n2. Testing query speed for case_id=2...")
case_id = 2

t0 = time.perf_counter()
with connection.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM blotter_kp_submission WHERE blotter_case_id = %s", [case_id])
    count = cur.fetchone()[0]
t1 = (time.perf_counter() - t0) * 1000
print(f"   Forms count query: {t1:.1f}ms ({count} forms)")
if t1 > 100:
    print("   [ERROR] TOO SLOW! Should be <10ms with indexes")

# Check 3: Audit data query
t0 = time.perf_counter()
with connection.cursor() as cur:
    cur.execute("""
        SELECT COUNT(*) 
        FROM blotter_kp_answer 
        WHERE field_id IN (1120, 1121, 1122)
          AND submission_id IN (
              SELECT submission_id FROM blotter_kp_submission WHERE blotter_case_id = %s
          )
    """, [case_id])
    count = cur.fetchone()[0]
t2 = (time.perf_counter() - t0) * 1000
print(f"   Audit data query: {t2:.1f}ms ({count} records)")
if t2 > 100:
    print("   [ERROR] TOO SLOW! Should be <20ms with indexes")

# Check 4: Current view code
print("\n3. Checking current view implementation...")
try:
    with open('lupon_mem/views_cases.py', 'r', encoding='utf-8') as f:
        content = f.read()
        if 'ULTRA-OPTIMIZED' in content or 'SINGLE ULTRA-FAST QUERY' in content:
            print("   [OK] Using optimized view code")
        else:
            print("   [ERROR] Still using OLD SLOW code!")
            print("   -> Replace case_detail function with optimized version")
except Exception as e:
    print(f"   ? Could not check: {e}")

# Check 5: Total time estimate
print("\n4. Estimated page load time:")
total_queries = 8  # Old code makes ~8 queries
avg_query_time = (t1 + t2) / 2
estimated_time = total_queries * avg_query_time / 1000
print(f"   Old code: ~{estimated_time:.1f}s ({total_queries} queries × {avg_query_time:.0f}ms)")
print(f"   Optimized: ~{max(t1, t2) / 1000:.1f}s (1 query)")

print("\n" + "=" * 60)
print("RECOMMENDATIONS:")
print("=" * 60)

if not indexes:
    print("1. ADD INDEXES IMMEDIATELY:")
    print("   psql -U postgres -d your_db -f sql\\case_detail_performance_indexes.sql")
    
if 'ULTRA-OPTIMIZED' not in content:
    print("2. REPLACE VIEW CODE:")
    print("   Copy code from views_cases_ultra_fast.py to views_cases.py")

print("\nAfter fixes, reload should be <2 seconds!")
