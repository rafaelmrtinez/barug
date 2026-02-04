# Center Year Field Fix

## Problem
The year "2025" was left-aligned in the field, making it look off-center.

## Solution
Set the year field to center alignment (Q=1) in both:
1. The PDF template itself
2. The PDF generation code (as a safeguard)

## Changes Made

### 1. Updated PDF Template
- Modified `pdf_templates/barangay-residency.pdf` to have center alignment for year field
- Field property `/Q` set to `1` (center)

### 2. Updated PDF Generation Code
Modified `clerk/services/pdf_service.py` in the `_fill_pdf_with_values` function:

```python
# Set center alignment for year field
from pypdf.generic import NumberObject
for page in writer.pages:
    annots = page.get('/Annots')
    if annots:
        for annot_ref in annots:
            annot = annot_ref.get_object()
            field_name = annot.get('/T')
            if field_name == 'year':
                annot[NameObject('/Q')] = NumberObject(1)  # 1 = center align
                print(f"[PDF DEBUG] Set year field to center alignment")
```

This ensures the year field is always centered, even if the template is replaced.

## Testing

1. **Restart Django server**
   ```bash
   python manage.py runserver
   ```

2. **Generate certificate**
   - Go to: http://127.0.0.1:8000/clerk/requests/317/
   - Click "Proceed" to download PDF
   - Open the PDF

3. **Verify**
   - Year "2025" should be centered in its field
   - Should look aligned with the rest of the text

## Quick Test
A test PDF has been created: `test_centered_year.pdf`
- Open it to verify the year is centered

## Alignment Values
- `/Q` = 0: Left align (default)
- `/Q` = 1: Center align (what we set)
- `/Q` = 2: Right align

## Files Modified
- ✅ `clerk/services/pdf_service.py` - Added center alignment code
- ✅ `pdf_templates/barangay-residency.pdf` - Updated with centered year field
- 🔧 `center_year_field.py` - Utility script (can be deleted)
- 🧪 `test_centered_year.pdf` - Test output (can be deleted)

## Status
✅ **FIXED** - Year field is now centered
