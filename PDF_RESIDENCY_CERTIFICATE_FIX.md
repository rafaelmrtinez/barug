# PDF Residency Certificate Fix

## Issues Identified

### 1. **Year Field Showing "2" Instead of "2025"**
**Problem**: The year field in the PDF template was too narrow (33 units wide) to display the full 4-digit year "2025", so it was being truncated to "2".

**Solution**: 
- Created a script (`fix_pdf_year_field.py`) to expand the year field width by 30 units
- Backed up the original template as `barangay-residency-backup.pdf`
- Replaced the original template with the fixed version
- The year field now has enough space to display "2025" properly

**Files Modified**:
- `pdf_templates/barangay-residency.pdf` (replaced with fixed version)
- `pdf_templates/barangay-residency-backup.pdf` (backup of original)
- `fix_pdf_year_field.py` (new utility script)

### 2. **Date of Residency Showing "No data"**
**Problem**: The code was looking for `date_of_residency` field in the line details, but the actual field name is `residency_since_text`.

**Solution**: 
- Modified `clerk/services/pdf_service.py` to use `residency_since_text` from line details
- Added fallback to construct the text from `residency_since_date` if `residency_since_text` is not available
- The field now properly displays "December 2021" or similar formatted text

**Files Modified**:
- `clerk/services/pdf_service.py` - Updated the residency certificate field mapping

### 3. **Age Showing "3" Instead of Actual Age**
**Problem**: The database has incorrect data - the `requester_age` is 3 because the person's birthdate in the database is set to 2021-12-02, making them appear 3 years old.

**Solution**: 
This is a **data issue**, not a code issue. The person record in the database needs to be corrected:
- Person ID: 4 (RAPHAEL HIZON BELLOSILLO)
- Current birthdate: 2021-12-02 (incorrect)
- This makes the calculated age: 3 years old

**Recommended Action**: Update the person's birthdate in the database to the correct value.

**Note**: The code is working correctly - it's calculating the age based on the birthdate in the database. The issue is with the data itself.

## Code Changes Summary

### `clerk/services/pdf_service.py`

1. **Added debugging to `_date_parts` function**:
   ```python
   def _date_parts(dt: datetime):
       day = dt.strftime("%d")
       month = dt.strftime("%B")
       year = dt.strftime("%Y")
       print(f"[DATE_PARTS DEBUG] Generated date parts: day={day}, month={month}, year={year}")
       return day, month, year
   ```

2. **Fixed residency certificate field mapping**:
   ```python
   if "residency" in doc_name:
       # Get residency information from line details
       details = line.get("details") or {}
       residency_since_text = _safe_str(details.get("residency_since_text") or "")
       
       # If residency_since_text is empty, try to construct from residency_since_date
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
       
       # ... rest of the code
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

## Testing

To test the fixes:

1. **Test the year field**:
   - Generate a new residency certificate
   - Verify that the year field shows "2025" (or current year) instead of "2"

2. **Test the date of residency**:
   - Generate a residency certificate for a person with residency data
   - Verify that the "date of residency" field shows the proper text (e.g., "December 2021")

3. **Age field**:
   - This will continue to show incorrect values until the database is fixed
   - To fix: Update the person's birthdate in the database to the correct value

## Utility Script

The `fix_pdf_year_field.py` script can be used to inspect and fix PDF form fields:

```bash
python fix_pdf_year_field.py
```

This script:
- Reads the PDF template
- Inspects all form fields
- Expands the year field width by 30 units
- Saves the fixed PDF as `barangay-residency-fixed.pdf`

## Rollback Instructions

If you need to rollback to the original PDF template:

```bash
cd pdf_templates
copy barangay-residency-backup.pdf barangay-residency.pdf
```

## Additional Notes

- The PDF form field width issue was caused by the original PDF template design
- The year field was only 33 units wide, which is too narrow for a 4-digit year
- The fixed version expands it to 63 units, which is sufficient for "2025"
- All other fields appear to be working correctly
