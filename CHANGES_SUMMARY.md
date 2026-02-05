# Date Filed Rename to Processed On - Summary

## Overview
This change renames the "Date Filed" column display to "Processed On" in the case list views, while ensuring the actual `date_filed` and `time_filed` columns from the database are properly used.

## Database Schema
The `blotter_case` table already has the correct columns:
- `date_filed` (DATE) - The actual date when the case was filed
- `time_filed` (TIME) - The actual time when the case was filed  
- `date_time_added` (TIMESTAMP) - When the record was added/processed in the system

## Changes Made

### 1. SQL Function (db_function_update.sql)
The `confirm_report_and_open_case` function already accepts:
- `p_date_filed DATE` - User-provided filing date
- `p_time_filed TIME` - User-provided filing time

These are used with COALESCE to default to CURRENT_DATE/CURRENT_TIME if not provided.

### 2. Views (views_cases.py)
Updated the `case_list` function query to:
- Changed column aliases from `date_filed_fmt` and `time_filed_fmt` to `processed_on_date` and `processed_on_time`
- These columns display `date_time_added` (when the case was processed/added to system)
- The actual `date_filed` and `time_filed` columns remain in the database for the actual filing date/time

**Before:**
```sql
TO_CHAR(bc.date_time_added AT TIME ZONE 'Asia/Manila', 'Mon DD, YYYY') AS date_filed_fmt,
TO_CHAR(bc.date_time_added AT TIME ZONE 'Asia/Manila', 'HH12:MI AM')   AS time_filed_fmt,
```

**After:**
```sql
TO_CHAR(bc.date_time_added AT TIME ZONE 'Asia/Manila', 'Mon DD, YYYY') AS processed_on_date,
TO_CHAR(bc.date_time_added AT TIME ZONE 'Asia/Manila', 'HH12:MI AM')   AS processed_on_time,
```

### 3. Templates
Updated table headers in:
- `case_list_offline.html` - Changed "Date Filed" to "Processed On"
- `case_list_fast.html` - Changed "Date Filed" to "Processed On"

## Data Flow

### When Creating a Case:
1. User provides `date_filed` and `time_filed` (or system uses current date/time)
2. System automatically sets `date_time_added` to NOW()
3. Both are stored in the database

### When Displaying Cases:
1. "Processed On" column shows `date_time_added` (when case was added to system)
2. The actual `date_filed` and `time_filed` are available in the database for reports/forms
3. Row indices in template: row.3 = processed_on_date, row.4 = processed_on_time

## JSON Data Example
From your provided data:
```json
{
  "date_filed": "2026-01-29",  // Actual filing date (stored in DB)
  "time_filed": "07:03:09",    // Actual filing time (stored in DB)
  "date_time_added": "2026-01-29 15:03:09.424914+08"  // When processed (displayed as "Processed On")
}
```

## Benefits
1. **Clarity**: "Processed On" better describes when the case was added to the system
2. **Accuracy**: Actual filing date/time are preserved in separate columns
3. **Flexibility**: Can show both "Processed On" (system timestamp) and "Date Filed" (user-provided) if needed
4. **No Data Loss**: All original data is preserved

## Files Modified
1. `d:\CAPSTONE 2\cloned_repo\barug\lupon_mem\views_cases.py`
2. `d:\CAPSTONE 2\cloned_repo\barug\lupon_mem\templates\lupon_mem\case_list_offline.html`
3. `d:\CAPSTONE 2\cloned_repo\barug\lupon_mem\templates\lupon_mem\case_list_fast.html`

## Testing Recommendations
1. Verify case list displays "Processed On" header
2. Confirm dates/times display correctly
3. Check that actual `date_filed` and `time_filed` are still accessible for forms/reports
4. Test case creation with and without provided date_filed/time_filed values
