# PDF Certificate Generation Fix - Complete Guide

## Summary

Fixed issues with the Barangay Residency Certificate PDF generation where fields were not being filled properly.

## Issues Fixed

### 1. ✅ Year Field Truncation (FIXED)
- **Problem**: Year showing "2" instead of "2025"
- **Root Cause**: PDF form field was only 33 units wide, too narrow for 4-digit year
- **Solution**: Expanded field to 63 units using `fix_pdf_year_field.py`
- **Files Changed**: 
  - `pdf_templates/barangay-residency.pdf` (replaced with fixed version)
  - `pdf_templates/barangay-residency-backup.pdf` (backup created)

### 2. ✅ Date of Residency Field (FIXED)
- **Problem**: Showing "No data" instead of "December 2021"
- **Root Cause**: Code was looking for `date_of_residency` but data has `residency_since_text`
- **Solution**: Updated `_fill_fields_for_line()` to use correct field name with fallback
- **Files Changed**: `clerk/services/pdf_service.py`

### 3. ⚠️ Age Field (DATA ISSUE - NOT FIXED)
- **Problem**: Showing "3" instead of actual age
- **Root Cause**: Database has incorrect birthdate (2021-12-02) for person_id=4
- **Solution Required**: Update database record with correct birthdate
- **Note**: Code is working correctly - this is a data quality issue

## Code Changes

### clerk/services/pdf_service.py

```python
# Added debugging to _date_parts
def _date_parts(dt: datetime):
    day = dt.strftime("%d")
    month = dt.strftime("%B")
    year = dt.strftime("%Y")
    print(f"[DATE_PARTS DEBUG] Generated date parts: day={day}, month={month}, year={year}")
    return day, month, year

# Fixed residency certificate field mapping
if "residency" in doc_name:
    details = line.get("details") or {}
    residency_since_text = _safe_str(details.get("residency_since_text") or "")
    
    # Fallback to construct from residency_since_date if text is empty
    if not residency_since_text:
        residency_date = details.get("residency_since_date")
        if residency_date:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(str(residency_date).replace('Z', '+00:00'))
                residency_since_text = dt.strftime("%B %Y")
            except Exception as e:
                print(f"[RESIDENCY DEBUG] Failed to parse residency_since_date: {e}")
                residency_since_text = ""
    
    result = {
        "name": subject_full_name,
        "age": subject_age,
        "addr": subject_addr,
        "date_of_residency": residency_since_text or "No data",
        "purpose": purpose,
        "date": d,
        "month": m,
        "year": y,
        "capt": captain,
        "amnt": paid_amt_str,
        "reciept": or_no or "—",
    }
```

## Utility Scripts Created

### 1. fix_pdf_year_field.py
Expands the year field in barangay-residency.pdf from 33 to 63 units.

**Usage**:
```bash
python fix_pdf_year_field.py
```

### 2. inspect_all_pdf_templates.py
Inspects all PDF templates and identifies potential field width issues.

**Usage**:
```bash
python inspect_all_pdf_templates.py
```

**Output**: Shows all form fields with their dimensions and flags potential issues.

## Testing

### Test Case 1: Year Field
1. Navigate to: http://127.0.0.1:8000/clerk/requests/317/
2. Click "Proceed" to download PDF
3. **Expected**: Year field shows "2025"
4. **Before Fix**: Showed "2"
5. **Status**: ✅ FIXED

### Test Case 2: Date of Residency
1. Same request as above
2. **Expected**: Shows "December 2021"
3. **Before Fix**: Showed "No data"
4. **Status**: ✅ FIXED

### Test Case 3: Age Field
1. Same request as above
2. **Current**: Shows "3"
3. **Expected**: Should show actual age (e.g., 24)
4. **Status**: ⚠️ REQUIRES DATABASE FIX

## Database Fix Required

To fix the age issue:

```sql
-- Check current data
SELECT person_id, first_name, last_name, birthdate, 
       EXTRACT(YEAR FROM AGE(birthdate)) as calculated_age
FROM person 
WHERE person_id = 4;

-- Update with correct birthdate (example)
UPDATE person 
SET birthdate = '2000-01-15'  -- Replace with actual birthdate
WHERE person_id = 4;
```

## Rollback Instructions

If you need to revert the PDF template changes:

```bash
cd pdf_templates
copy barangay-residency-backup.pdf barangay-residency.pdf
```

Then restart Django server:
```bash
python manage.py runserver
```

## Additional Findings

The inspection script found one other potential issue:

- **barangay-death-cert.pdf**: `date_of_death` field is 39.4 units wide (borderline narrow)
  - May need expansion if dates are being truncated
  - Can use `fix_pdf_year_field.py` as a template to fix

## Files Created/Modified

### Created:
- `fix_pdf_year_field.py` - PDF field expansion utility
- `inspect_all_pdf_templates.py` - PDF template inspection tool
- `PDF_RESIDENCY_CERTIFICATE_FIX.md` - Detailed fix documentation
- `QUICK_FIX_SUMMARY.md` - Quick reference guide
- `README_PDF_FIX.md` - This file
- `pdf_templates/barangay-residency-backup.pdf` - Backup of original

### Modified:
- `clerk/services/pdf_service.py` - Fixed residency field mapping
- `pdf_templates/barangay-residency.pdf` - Expanded year field

## Maintenance Notes

1. **PDF Template Updates**: When updating PDF templates, always check field widths using `inspect_all_pdf_templates.py`
2. **Year Fields**: Should be at least 50-60 units wide for 4-digit years
3. **Date Fields**: Should be at least 60-80 units wide for full dates
4. **Testing**: Always test PDF generation after template changes

## Support

For questions or issues:
1. Check the debug output in Django console (look for `[PDF DEBUG]` and `[RESIDENCY DEBUG]` messages)
2. Run `inspect_all_pdf_templates.py` to check field dimensions
3. Review this documentation for common issues and solutions
