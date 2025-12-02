# Case Status and Settlement Status Update Functions

## Overview
This document lists all the specific functions and database functions used for updating case status and settlement status in the Lupon Member module.

---

## 1. Settlement Status Update

### Django View Function
**File:** `lupon_mem/views_cases.py`  
**Function:** `case_settlement_update(request: HttpRequest, case_id: int)` (Line 652)

**URL Routes:**
- `/lupon_mem/cases/<int:case_id>/settlement`
- `/lupon_mem/cases/<int:case_id>/update-settlement/`

**Parameters:**
- `settlement_status` - The new settlement status name (from POST)
- `remarks` - Optional remarks (from POST)
- `staff_id` - Current staff ID (from session)

### Database Function (PostgreSQL)
**Function:** `fn_set_case_settlement(case_id, status_name, remarks, staff_id)`

**SQL Call:**
```sql
SELECT * FROM fn_set_case_settlement(%s, %s, %s, %s)
```

**Returns:** `(ok, case_id, new_status, changed_at)`

**What it does:**
- Updates the `settlement_status_id` in the `blotter_case` table
- Logs the change with timestamp
- Returns success status and new settlement status name

---

## 2. Case Close (Change Case State to CLOSED)

### Django View Function
**File:** `lupon_mem/views_cases.py`  
**Function:** `case_close(request: HttpRequest, case_id: int)` (Line 739)

**URL Route:**
- `/lupon_mem/cases/<int:case_id>/close`

**Parameters:**
- `close_note` - Optional note about why case is being closed (from POST)
- `staff_id` - Current staff ID (from session)

### Service Function
**File:** `lupon_mem/services/case_state.py`  
**Function:** `close_case(blotter_case_id: int, staff_id: int, note: str | None = None)`

### Database Function (PostgreSQL)
**Function:** `close_blotter_case(p_case_id, p_by_staff_id, p_close_note)`

**SQL Call:**
```sql
SELECT close_blotter_case(%s, %s, %s)
```

**What it does:**
- Sets `case_state_id` to CLOSED in the `blotter_case` table
- Stamps `closed_at` timestamp
- Records `closed_by_staff_id`
- Stores optional `close_note`

---

## 3. Case Reopen (Change Case State to OPEN)

### Django View Function
**File:** `lupon_mem/views_cases.py`  
**Function:** `case_reopen(request: HttpRequest, case_id: int)` (Line 803)

**URL Route:**
- `/lupon_mem/cases/<int:case_id>/reopen`

**Parameters:**
- `reopen_reason` - Optional reason for reopening (from POST)
- `staff_id` - Current staff ID (from session)

### Service Function
**File:** `lupon_mem/services/case_state.py`  
**Function:** `reopen_case(blotter_case_id: int, staff_id: int, reason: str | None = None)`

### Database Function (PostgreSQL)
**Function:** `reopen_blotter_case(p_case_id, p_by_staff_id, p_reason)`

**SQL Call:**
```sql
SELECT reopen_blotter_case(%s, %s, %s)
```

**What it does:**
- Sets `case_state_id` back to OPEN in the `blotter_case` table
- Clears `closed_at` timestamp
- Clears `closed_by_staff_id`
- Stores optional `reopen_reason`

---

## 4. Additional Case State Update

### Django View Function
**File:** `lupon_mem/views_case_state.py`  
**Function:** `update_case_state(request, case_id)`

**URL Route:**
- `/lupon_mem/cases/<int:case_id>/update-case-state/`

**Note:** This is imported in urls.py but is a separate view for more general case state updates.

---

## Logging

All three operations (settlement update, close, reopen) use the logging utility:

**File:** `lupon_mem/utils/logging.py`  
**Function:** `blotter_log_event(...)`

**Parameters logged:**
- `action` - "UPDATE_SETTLEMENT", "CLOSE_CASE", or "REOPEN_CASE"
- `table_affected` - "blotter_case"
- `record_affected_id` - The case ID
- `details` - Human-readable message with staff name, case number, and notes
- `performer_staff_id` - Who performed the action
- `field_changed` - "settlement_status" or "case_state"
- `old_value` - Previous status/state
- `new_value` - New status/state

---

## Summary Table

| Action | Django View | Service Function | Database Function |
|--------|-------------|------------------|-------------------|
| **Update Settlement** | `case_settlement_update()` | N/A (direct SQL) | `fn_set_case_settlement()` |
| **Close Case** | `case_close()` | `close_case()` | `close_blotter_case()` |
| **Reopen Case** | `case_reopen()` | `reopen_case()` | `reopen_blotter_case()` |

---

## Database Tables Affected

1. **blotter_case** table:
   - `settlement_status_id` - Updated by settlement update
   - `case_state_id` - Updated by close/reopen
   - `closed_at` - Timestamp when closed
   - `closed_by_staff_id` - Staff who closed the case
   - `close_note` / `reopen_reason` - Optional notes

2. **settlement_status** table (lookup):
   - Contains settlement status options (e.g., "SETTLED", "UNSETTLED", "PENDING")

3. **case_state** table (lookup):
   - Contains case state options (e.g., "OPEN", "CLOSED", "PENDING")

---

## Modal Forms (Frontend)

The modals are defined in the case detail templates:
- `updateSettlementModal` - For updating settlement status
- `closeCaseModal` - For closing a case
- `reopenCaseModal` - For reopening a case

These modals POST to the respective URLs listed above.
