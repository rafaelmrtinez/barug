# Blotter Report Sort Order Fix

## Summary
Fixed the blotter report list to display in descending order (newest first, 7→1) by default.

## Changes Made

### File: `lupon_mem/views_reports.py`

**Line ~247:** Changed default sort parameter
```python
# BEFORE
f_sort = (request.GET.get("sort") or "oldest").strip()

# AFTER
f_sort = (request.GET.get("sort") or "newest").strip()
```

**Line ~315:** Fixed sort logic
```python
# BEFORE
# Apply sorting
if f_sort == "newest":
    filtered_reports.reverse()

# AFTER
# Apply sorting (default is newest first - DESC order)
if f_sort == "oldest":
    filtered_reports.reverse()  # Reverse to get oldest first (ASC)
```

## How It Works

### Database Query
```python
# Already orders by DESC (newest first)
cur.execute("SELECT ... FROM blotter_report ORDER BY blotter_report_id DESC")
```

### Sort Logic
1. **Default (no sort parameter):** Shows DESC order (7, 6, 5, 4, 3, 2, 1)
2. **sort=newest:** Shows DESC order (7, 6, 5, 4, 3, 2, 1)
3. **sort=oldest:** Reverses to ASC order (1, 2, 3, 4, 5, 6, 7)

## Result

### Before Fix
- Default showed: 1, 2, 3, 4, 5, 6, 7 (oldest first)
- User had to manually select "newest" to see 7, 6, 5, 4, 3, 2, 1

### After Fix
- Default shows: 7, 6, 5, 4, 3, 2, 1 (newest first) ✅
- User can select "oldest" to see 1, 2, 3, 4, 5, 6, 7

## URL
http://192.168.8.107:8005/lupon_mem/reports/

## Testing
1. Visit the reports page without any parameters
2. **Expected:** Reports displayed in DESC order (newest first)
3. Select "Oldest First" from sort dropdown
4. **Expected:** Reports displayed in ASC order (oldest first)
