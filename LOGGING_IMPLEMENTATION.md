# Blotter Log Event Implementation

This document outlines the implementation of the `blotter_log_event` logging functionality across the lupon_mem module.

## Database Function

The `blotter_log_event` function was created in Supabase with the following signature:

```sql
CREATE OR REPLACE FUNCTION blotter_log_event(
    p_action              text,
    p_table_affected      text,
    p_record_affected_id  bigint,
    p_details             jsonb  DEFAULT '{}'::jsonb,
    p_performer_staff_id  integer DEFAULT NULL,
    p_performer_person_id integer DEFAULT NULL,
    p_field_changed       text   DEFAULT NULL,
    p_old_value           text   DEFAULT NULL,
    p_new_value           text   DEFAULT NULL
)
RETURNS void
```

## Python Utility Function

Created `lupon_mem/utils/logging.py` with a helper function that wraps the database function call:

```python
def blotter_log_event(
    action: str,
    table_affected: str,
    record_affected_id: int,
    details: Optional[Dict[str, Any]] = None,
    performer_staff_id: Optional[int] = None,
    performer_person_id: Optional[int] = None,
    field_changed: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None
) -> None
```

## Implementation Locations

### 1. Case Management (views_cases.py)

- **Case Creation**: Logs when new blotter cases are created
- **Settlement Status Updates**: Logs changes to case settlement status
- **Case Closure**: Logs when cases are closed
- **Case Reopening**: Logs when cases are reopened

### 2. Form Management (views.py)

- **Auto-generated Forms**: Logs creation of settlement summaries (MEDx-SETTLED)
- **Form Submissions**: Logs when forms are submitted from prefill
- **KP-16 Draft Creation**: Logs creation of settlement agreement drafts
- **MED-ATT-2025 Draft Creation**: Logs creation of mediation attendance drafts

### 3. Hearing Management (views.py)

- **Mediation Completion**: Logs when mediation hearings are completed
- **Conciliation Completion**: Logs when conciliation hearings are completed
- **Summon Attendance**: Logs updates to summon attendance status

### 4. API Operations (views_api.py)

- **Draft Creation**: Logs when draft submissions are created via API
- **Form Submission**: Logs when forms are submitted via API

### 5. Blotter Reports (views_reports.py)

- **Report Creation**: Logs when new blotter reports are filed
- **Report Approval**: Logs when reports are approved by Lupon
- **Report Decline**: Logs when reports are declined by Lupon
- **Case Creation from Report**: Logs when cases are created from reports
- **Payment Processing**: Logs when payments are recorded for reports

## Logged Actions

### CREATE Actions
- New blotter cases
- New blotter reports
- New form submissions (drafts and final)
- Case progress tracking entries
- Auto-generated settlement summaries
- Cases created from reports

### UPDATE Actions
- Settlement status changes
- Case state changes (close/reopen)
- Form status changes (draft → submitted)
- Summon attendance updates
- Report approval/decline actions
- Payment status updates

## Log Details

Each log entry includes:
- **Action**: Type of operation (CREATE, UPDATE, DELETE)
- **Table Affected**: Database table that was modified
- **Record ID**: Primary key of the affected record
- **Details**: JSON object with additional context
- **Performer**: Staff ID of the person performing the action
- **Field Changes**: Specific field that was changed (for updates)
- **Old/New Values**: Previous and new values (for updates)

## Usage Examples

```python
# Log case creation
blotter_log_event(
    action="CREATE",
    table_affected="blotter_case",
    record_affected_id=case_id,
    details={
        "case_name": blotter_case_name,
        "complaint_title_id": complaint_title_id,
        "complainants_count": len(complainants),
        "respondents_count": len(respondents)
    },
    performer_staff_id=staff_id
)

# Log form submission
blotter_log_event(
    action="UPDATE",
    table_affected="blotter_kp_submission",
    record_affected_id=submission_id,
    details={"case_id": case_id, "form_code": form_code},
    performer_staff_id=staff_id,
    field_changed="status",
    old_value="DRAFT",
    new_value="SUBMITTED"
)

# Log report creation
blotter_log_event(
    action="CREATE",
    table_affected="blotter_report",
    record_affected_id=report_id,
    details={
        "incident_subject": incident_subject,
        "complainant_id": complainant_id,
        "respondent_count": len(respondent_ids)
    },
    performer_staff_id=staff_id
)

# Log report approval
blotter_log_event(
    action="UPDATE",
    table_affected="blotter_report",
    record_affected_id=report_id,
    details={"action": "APPROVED", "payment_status": "UNPAID"},
    performer_staff_id=staff_id,
    field_changed="payment_status",
    new_value="UNPAID"
)
```

## Error Handling

The logging utility includes error handling to ensure that logging failures don't break the main application functionality. If logging fails, an error is printed but the main operation continues.

## Benefits

1. **Audit Trail**: Complete record of all actions performed in the system
2. **Accountability**: Track who performed what actions and when
3. **Debugging**: Easier troubleshooting with detailed operation logs
4. **Compliance**: Meet audit requirements for case management systems
5. **Analytics**: Data for system usage analysis and reporting