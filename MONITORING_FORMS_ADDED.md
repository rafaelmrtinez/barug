# Monitoring Forms Added to Form Chooser

## Summary
Added the monitoring forms (form_id 35 and 36) to the case form chooser at `/lupon_mem/cases/{case_id}/forms/choose/`.

## Changes Made

### File: `lupon_mem/views.py`
**Function:** `add_form_choose_static(request, case_id: int)`
**Line:** ~1755

Added two new forms to the `all_forms` list:
- `('MON-COMPL', 'MONITORING (COMPLAINANT)')` - form_id 35
- `('MON-RESP', 'MONITORING (RESPONDENT)')` - form_id 36

### Updated Form List
The form chooser now displays 7 forms (previously 5):
1. KP-9-P2 - SUMMON FOR THE RESPONDENT - PAGE 2
2. KP-10 - NOTICE FOR CONSTITUTION OF PANGKAT
3. KP-11 - NOTICE TO CHOSEN PANGKAT MEMBER
4. KP-13 - SUBPOENA LETTER
5. MINUTES - MINUTES OF HEARING
6. **MON-COMPL - MONITORING (COMPLAINANT)** ← NEW
7. **MON-RESP - MONITORING (RESPONDENT)** ← NEW

## Form Details
Based on the provided JSON data:

### Form 35 - MON-COMPL
- **Form Code:** MON-COMPL
- **Form Name:** MONITORING (COMPLAINANT)
- **Template Path:** kp_forms/monitoring_of_case_complainant.pdf
- **Version:** 1
- **Status:** Active
- **Created:** 2025-10-08 17:34:46

### Form 36 - MON-RESP
- **Form Code:** MON-RESP
- **Form Name:** MONITORING (RESPONDENT)
- **Template Path:** kp_forms/monitoring_of_case_respondent.pdf
- **Version:** 1
- **Status:** Active
- **Created:** 2025-10-08 17:34:46

## How to Use
1. Navigate to a case detail page
2. Click "Add Form" or go to `/lupon_mem/cases/{case_id}/forms/choose/`
3. The monitoring forms will now appear in the list
4. Click "Use this form" on either monitoring form to create a submission

## Template Integration
The forms are already integrated with the template system:
- The template at `lupon_mem/templates/lupon_mem/add_form_choose_static.html` will automatically display the new forms
- The forms use the same styling and interaction patterns as existing forms
- Search functionality will work with the new form codes and names

## Database Requirements
The forms must exist in the `kp_form` table with:
- `form_code` = 'MON-COMPL' or 'MON-RESP'
- `is_active` = TRUE
- Corresponding PDF templates in the `static/kp_forms/` directory

## Testing
To verify the changes:
1. Access: `http://192.168.8.107:8005/lupon_mem/cases/2/forms/choose/`
2. Confirm both monitoring forms appear in the list
3. Test the search functionality with "MON" or "MONITORING"
4. Click "Use this form" to ensure the form builder loads correctly

## Notes
- The forms are displayed in the order they appear in the `all_forms` list
- The pagination is set to 10 forms per page (currently all 7 fit on one page)
- The forms follow the same workflow as other KP forms
- No database migrations are required as the forms already exist in the database
