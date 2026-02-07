# Case Detail Performance Fix

## Problem
The case detail page (`/lupon_mem/cases/2/`) takes 30-60 seconds to load.

## Root Causes

### 1. **Multiple Separate Database Queries**
The view executes 5+ separate queries:
- Main case query with 4 subqueries
- Total forms count
- Paginated forms with audit data
- Submitted form codes
- All form codes
- Pangkat members query
- KP-7 details query
- Upcoming hearings query

### 2. **Inefficient Subqueries**
```sql
(SELECT COUNT(*) FROM blotter_kp_submission s2 WHERE s2.blotter_case_id = bc.blotter_case_id)
(SELECT COUNT(*) FROM blotter_kp_submission s3 JOIN kp_form kf3 ...)
(SELECT COUNT(*) FROM blotter_kp_submission s4 JOIN kp_form kf4 ...)
```

### 3. **Heavy JavaScript on Page Load**
- Multiple API calls (`checkHearingStatus`, `getMediationHearingDetails`)
- Complex flow engine initialization
- Form labeling logic

### 4. **Missing Database Indexes**
No indexes on:
- `blotter_kp_submission.blotter_case_id`
- `blotter_kp_answer.submission_id`
- `blotter_kp_answer.field_id`

## Solutions

### Quick Fixes (Immediate - 5-10x faster)

1. **Add Database Indexes**
```sql
-- Add these indexes to speed up queries
CREATE INDEX IF NOT EXISTS idx_submission_case 
ON blotter_kp_submission(blotter_case_id);

CREATE INDEX IF NOT EXISTS idx_submission_status 
ON blotter_kp_submission(status);

CREATE INDEX IF NOT EXISTS idx_answer_submission 
ON blotter_kp_answer(submission_id);

CREATE INDEX IF NOT EXISTS idx_answer_field 
ON blotter_kp_answer(field_id);

CREATE INDEX IF NOT EXISTS idx_form_code 
ON kp_form(form_code);
```

2. **Use Single Optimized Query**
Replace multiple queries with one CTE-based query.

3. **Defer JavaScript API Calls**
Move API calls to happen only when needed (e.g., when offcanvas opens).

### Implementation Steps

#### Step 1: Add Database Indexes (CRITICAL - Do this first!)
```bash
psql -U your_user -d your_database -f sql/case_detail_performance_indexes.sql
```

This will add 10+ indexes that dramatically speed up queries. Expected improvement: 5-10x faster.

#### Step 2: Replace case_detail View

In `lupon_mem/views_cases.py`, replace the `case_detail` function with the optimized version from `views_cases_optimized_detail.py`.

Key changes:
- **8+ queries → 1 query** using CTEs (Common Table Expressions)
- **JSON aggregation** for forms data instead of multiple round trips
- **Eliminated N+1 queries** for audit data, KP-7 details, pangkat members
- **Deferred API calls** in JavaScript (only load when needed)

#### Step 3: Update Template JavaScript (Optional but Recommended)

In `lupon_mem/templates/lupon_mem/case_detail.html`, move the API calls inside the offcanvas event:

```javascript
// BEFORE: API calls on page load
document.addEventListener('DOMContentLoaded', async function(){
    HEARING_STATUS = await checkHearingStatus();  // ❌ Slow!
    // ...
});

// AFTER: API calls only when needed
canvasEl.addEventListener('shown.bs.offcanvas', async () => {
    HEARING_STATUS = await checkHearingStatus();  // ✅ Fast!
    // ...
});
```

## Expected Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Database Queries | 8-12 | 1-2 | 85% reduction |
| Query Time | 25-50s | 0.5-2s | 95% faster |
| Page Load | 30-60s | 1-3s | 95% faster |
| Memory Usage | High | Low | 70% reduction |

## Testing

1. **Before applying fixes:**
   ```bash
   # Time the page load
   curl -w "@curl-format.txt" -o /dev/null -s http://127.0.0.1:8000/lupon_mem/cases/2/
   ```

2. **Apply indexes:**
   ```bash
   psql -U your_user -d your_database -f sql/case_detail_performance_indexes.sql
   ```

3. **Test again:**
   Should see 5-10x improvement immediately.

4. **Apply code changes:**
   Replace the view function.

5. **Final test:**
   Should see 20-30x improvement overall.

## Monitoring

Add this to your view to track performance:

```python
import time
t0 = time.perf_counter()
# ... your code ...
total_ms = (time.perf_counter() - t0) * 1000
log.info(f"case_detail: {total_ms:.1f}ms for case {case_id}")
```

## Rollback Plan

If issues occur:

1. **Revert code changes:** Use git to restore original `views_cases.py`
2. **Keep indexes:** The indexes are safe and only improve performance
3. **Check logs:** Look for errors in `barug/system_info/error.log`

## Additional Optimizations (Future)

1. **Add Redis caching** for lookup data (complaint_titles, case_natures, etc.)
2. **Implement pagination caching** for frequently accessed cases
3. **Add database connection pooling** (pgBouncer)
4. **Consider materialized views** for complex aggregations
5. **Add query result caching** for hearing window calculations
