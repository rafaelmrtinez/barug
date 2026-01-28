# Quick Guide: Deleting Forms

## What Was Added

✅ **Delete button** for each form in the case detail page  
✅ **Confirmation dialog** to prevent accidental deletions  
✅ **Automatic cleanup** of all form answers (CASCADE delete)  
✅ **Role-based access** (hidden for Barangay Secretary)  
✅ **Error handling** with user-friendly messages  

## How to Use

1. Go to case detail page: `http://127.0.0.1:8000/lupon_mem/cases/1/`
2. Find the form you want to delete in the table
3. Click the **red trash icon** (🗑️) in the Actions column
4. Confirm deletion in the popup dialog
5. Form and all its data will be permanently deleted

## Important Notes

⚠️ **Deletion is permanent** - Cannot be undone  
⚠️ **All answers are deleted** - Due to CASCADE constraint  
⚠️ **Secretary role cannot delete** - Button is hidden  

## Files Changed

- `lupon_mem/views_delete_submission.py` - NEW delete view
- `lupon_mem/urls.py` - Added delete URL route
- `lupon_mem/templates/lupon_mem/case_detail.html` - Added delete button & JS

## URL Endpoint

```
POST /lupon_mem/submissions/<submission_id>/delete/
```

## Database Impact

When you delete a submission:
- ✅ `blotter_kp_submission` record deleted
- ✅ All `blotter_kp_answer` records deleted automatically (CASCADE)
- ✅ No orphaned data left behind

## Example

If you wrongly entered a KP-7 form:
1. Navigate to the case
2. Find "KP-7 - Complaint Form" in the table
3. Click the trash icon
4. Confirm "Are you sure you want to delete this form?"
5. Done! The form is removed from the case

---

**Need more details?** See `FORM_DELETION_FEATURE.md`
