# Barangay Captain Name - Dynamic Fetch

## Problem
The barangay captain name was hardcoded as "Lourdes R. Ramirez" instead of being fetched from the database.

## Solution
Added a function to fetch the current barangay captain from the database dynamically.

## Implementation

### New Function: `_get_barangay_captain_name()`

Located in `clerk/services/pdf_service.py`:

```python
def _get_barangay_captain_name() -> str:
    """Fetch the current barangay captain name from database"""
    try:
        # Get active staff with role_id=3 (Barangay Captain)
        result = supabase.table("staff").select("person_id").eq("role_id", 3).eq("acc_status_id", 1).limit(1).execute()
        if result.data and len(result.data) > 0:
            person_id = result.data[0].get("person_id")
            if person_id:
                # Get person details
                person_result = supabase.table("person").select("first_name, middle_name, last_name, suffix").eq("person_id", person_id).single().execute()
                if person_result.data:
                    first = _safe_str(person_result.data.get("first_name", ""))
                    middle = _safe_str(person_result.data.get("middle_name", ""))
                    last = _safe_str(person_result.data.get("last_name", ""))
                    suffix = _safe_str(person_result.data.get("suffix", ""))
                    
                    # Format: First M. Last Suffix
                    middle_initial = f"{middle[0]}." if middle else ""
                    name_parts = [first, middle_initial, last]
                    if suffix:
                        name_parts.append(suffix)
                    captain_name = " ".join(p for p in name_parts if p)
                    return captain_name
    except Exception as e:
        print(f"[CAPTAIN DEBUG] Failed to fetch captain name: {e}")
    
    # Fallback to default
    return "Lourdes R. Ramirez"
```

### How It Works

1. **Queries staff table** for active barangay captain (role_id=3, acc_status_id=1)
2. **Gets person_id** from staff record
3. **Fetches person details** (first_name, middle_name, last_name, suffix)
4. **Formats name** as "FIRST M. LAST SUFFIX"
5. **Falls back** to "Lourdes R. Ramirez" if fetch fails

### Current Captain

Based on the database:
- **Staff ID**: 20
- **Person ID**: 233
- **Name**: KIMBERLY D. DAYUJA
- **Role**: Barangay Captain (role_id=3)
- **Status**: Active (acc_status_id=1)

## Testing

Run the test script:
```bash
python test_captain_fetch.py
```

Expected output:
```
Captain Name: KIMBERLY D. DAYUJA
[OK] Successfully fetched captain name from database
```

## Usage

The captain name is automatically fetched when generating any certificate. No manual intervention needed.

### In Code

```python
captain = _safe_str(header.get("captain_name") or _get_barangay_captain_name())
```

This checks:
1. First: `header.get("captain_name")` (if provided in request)
2. Then: `_get_barangay_captain_name()` (fetch from database)
3. Finally: Falls back to "Lourdes R. Ramirez" if both fail

## Files Modified

- ✅ `clerk/services/pdf_service.py` - Added `_get_barangay_captain_name()` function
- ✅ `clerk/services/pdf_service.py` - Updated `_fill_fields_for_line()` to use dynamic fetch
- 🧪 `test_captain_fetch.py` - Test script (can be deleted)

## Benefits

1. **Dynamic**: Automatically updates when captain changes in database
2. **Reliable**: Has fallback to default name if fetch fails
3. **Consistent**: All certificates use the same captain name from database
4. **Maintainable**: No need to update code when captain changes

## Restart Required

After this change, restart the Django server:
```bash
python manage.py runserver
```

## Status

✅ **IMPLEMENTED** - Captain name is now fetched from database
