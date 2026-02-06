# Form Data Priority - UI/Frontend First

## Summary
The form builder system is already correctly configured to **NEVER override UI/Frontend data**. User input from the form interface has absolute priority over any prefill or auto-computed values.

## Data Priority Order

### 1. UI/Frontend Data (HIGHEST PRIORITY) ✅
- **Source:** User input in the form builder interface
- **Storage:** `blotter_kp_answer` table
- **When:** User fills out fields and clicks save/submit
- **Priority:** ABSOLUTE - Never overridden

### 2. Handler Values (Form-specific logic)
- **Source:** Form-specific handlers (e.g., KP-24)
- **When:** Only used if no UI data exists
- **Priority:** Medium

### 3. Prefill Values (LOWEST PRIORITY)
- **Source:** Case data, party names, dates, etc.
- **When:** Only used if no UI data and no handler values exist
- **Priority:** Fallback only

## Code Flow

### Save Process (views_api.py - save_answers)
```python
# User fills form → POST request with answers
payload = json.loads(data["answers"])  # {field_id: value}

# Save to database with UPSERT
INSERT INTO blotter_kp_answer(submission_id, field_id, value_json)
VALUES (%s,%s,%s)
ON CONFLICT (submission_id, field_id)
DO UPDATE SET value_json=EXCLUDED.value_json  # ← UI data overwrites everything
```

### Load Process (form_builder_service.py - apply_answers_and_prefills)
```python
def _ans_or_prefill(field_id, label, code):
    v = answers.get(str(field_id))
    
    # PRIORITY 1: UI/Frontend data - NEVER override user input
    if v not in (None, "", "null"):
        return v  # ← UI data returned immediately
    
    # PRIORITY 2: Handler values (only if no UI data)
    if handler_values:
        # ... check handler values
    
    # PRIORITY 3: Prefill values (only if no UI data and no handler values)
    return prefill_by_label.get(key) or prefill_by_code.get(ckey, "")
```

## Key Points

### ✅ What IS Protected
- Any field the user fills in the UI
- Any field the user modifies in the UI
- Any field saved via the form builder interface

### ✅ What Happens on Form Load
1. System checks for saved answers (UI data)
2. If saved answer exists → Use it (ALWAYS)
3. If no saved answer → Try handler values
4. If no handler values → Use prefill values

### ✅ What Happens on Form Save
1. User clicks "Save" or "Submit"
2. All field values from UI sent to server
3. Values saved to database with UPSERT
4. Existing values are overwritten with new UI values

## Example Scenario

### Scenario: User fills "Complainant Name" field

1. **Initial Load (New Form)**
   - No saved answer exists
   - System uses prefill: "Juan Dela Cruz"
   - Field shows: "Juan Dela Cruz"

2. **User Edits Field**
   - User changes to: "Maria Santos"
   - User clicks "Save"
   - System saves: "Maria Santos" to database

3. **Form Reload**
   - System checks saved answers
   - Finds: "Maria Santos" (UI data)
   - Field shows: "Maria Santos" ← UI data preserved
   - Prefill "Juan Dela Cruz" is IGNORED

4. **User Edits Again**
   - User changes to: "Pedro Reyes"
   - User clicks "Save"
   - System saves: "Pedro Reyes" to database
   - Previous value "Maria Santos" is overwritten

## Technical Implementation

### Database Schema
```sql
-- Unique constraint ensures one answer per field per submission
CREATE UNIQUE INDEX ON blotter_kp_answer (submission_id, field_id);

-- UPSERT operation
INSERT INTO blotter_kp_answer(submission_id, field_id, value_json)
VALUES (123, 456, '"User Input"')
ON CONFLICT (submission_id, field_id)
DO UPDATE SET value_json = EXCLUDED.value_json;
```

### Priority Check Function
```python
# Location: lupon_mem/services/form_builder_service.py
# Function: apply_answers_and_prefills

def _ans_or_prefill(field_id, label, code):
    # Step 1: Check saved answers (UI data)
    v = answers.get(str(field_id))
    if v not in (None, "", "null"):
        return v  # ← UI data wins, function returns immediately
    
    # Step 2: Only reached if no UI data exists
    # ... check handler values and prefills
```

## Verification

### How to Verify UI Data Priority
1. Open form: `http://192.168.8.107:8005/lupon_mem/cases/2/forms/37/build/`
2. Fill in a field with custom value
3. Click "Save"
4. Refresh the page
5. **Expected:** Your custom value is still there (not replaced by prefill)

### Debug Logging
The system already has debug output:
```python
# In apply_answers_and_prefills
print(f"[DEBUG] Field {field_id}: saved={v}, prefill={prefill_value}")
```

## Conclusion

**The system is already correctly configured.** UI/Frontend data has absolute priority and will never be overridden by prefill values. The only way to change a field value is:
1. User manually edits it in the UI
2. User clicks "Save" or "Submit"

No automatic process will override user input.

## Files Modified

### lupon_mem/services/form_builder_service.py
- Added clarifying comment in `_ans_or_prefill` function
- No logic changes - only documentation improvement
- Line ~370: Enhanced comment to emphasize UI data priority

## Related Files (No Changes Needed)
- `lupon_mem/views_api.py` - save_answers function (already correct)
- `lupon_mem/views.py` - form_builder view (already correct)
- `lupon_mem/templates/lupon_mem/form_builder.html` - UI (already correct)
