This document explains the migration of form POST logic from `maternal/views.py` into separate class-based API endpoints under `maternal/api/`.

Summary of changes
- Moved POST handlers for the following forms into their own class-based endpoints (each file under `maternal/api/`):
  - Obstetric -> `obstetric_api.py` -> `ObstetricHistoryAPI`
  - Medical History -> `medical_history_api.py` -> `MedicalHistoryAPI`
  - Previous Pregnancy -> `previous_pregnancy_api.py` -> `PreviousPregnancyAPI`
  - Tetanus Toxoid -> `tetanus_toxoid_api.py` -> `TetanusToxoidAPI`
  - Present Pregnancy -> `present_pregnancy_api.py` -> `PresentPregnancyAPI`
  - Checklist -> `checklist_api.py` -> `CheckListAPI`
  - Plans -> `plans_api.py` -> `PlansAPI`
  - Micronutrients -> `micronutrients_api.py` -> `MicroNutrientsAPI`
  - Prenatal Follow-up Entry -> `prenatal_followup_api.py` -> `PrenatalFollowUpEntryAPI`

- The view `maternal_health_record_form` in `maternal/views.py` is now display-only and accepts GET only. Any POSTs should go to the new API endpoints.
- The previous `prenatal_api` function inside `maternal/views.py` was removed and replaced by the class-based `PrenatalFollowUpEntryAPI` in `maternal/api/prenatal_followup_api.py`.
- `maternal/urls.py` was updated to register the new routes (class-based views) and to point the prenatal API route to the new class.

Design notes
- Forms in `maternal/forms/` are used as "serializers": each API view instantiates the corresponding form with incoming data, calls `is_valid()`, and uses `cleaned_data` to call repository methods.
- All endpoints are class-based (`django.views.View`) and decorated with `@session_login_required`, `@role_required(...)`, and `@nocache` using `method_decorator`.
- Payloads: the endpoints accept either JSON payloads (Content-Type: application/json) or standard form-encoded POST data.

API endpoint behavior (what each endpoint does)
- `ObstetricHistoryAPI` (`/api/v1/mhr/obstetric/`): Validates obstetric fields, inserts obstetric history using `REPOSITORY.insert_obstetric_history`.
- `MedicalHistoryAPI` (`/api/v1/mhr/medical-history/`): Validates medical history, inserts via `REPOSITORY.insert_medical_history`.
- `PreviousPregnancyAPI` (`/api/v1/mhr/previous-pregnancy/`): Validates a single previous pregnancy entry and inserts via `REPOSITORY.insert_previous_pregnancy_info`.
- `TetanusToxoidAPI` (`/api/v1/mhr/tetanus-toxoid/`): Validates tetanus fields and inserts via `REPOSITORY.insert_maternal_tt_record`.
- `PresentPregnancyAPI` (`/api/v1/mhr/present-pregnancy/`): Validates present pregnancy summary (gravida/para/lmp/edc) and inserts via `REPOSITORY.insert_present_pregnancy_status`.
- `CheckListAPI` (`/api/v1/mhr/checklist/`): Validates checklist items and inserts via `REPOSITORY.insert_checklist_items`.
- `PlansAPI` (`/api/v1/mhr/plans/`): Validates plan fields and inserts via `REPOSITORY.insert_plan_and_baseline`.
- `MicroNutrientsAPI` (`/api/v1/mhr/micronutrients/`): Validates micronutrients/iron/deworming and inserts via `REPOSITORY.insert_micronutrients`.
- `PrenatalFollowUpEntryAPI` (`/api/form/prenatal/` & `/api/v1/...`): Validates prenatal follow-up entry and either inserts anc row findings (BHW role) or calls an update path for midwife role.

Developer notes and next steps
- The repository methods are called exactly as the previous monolithic view did; ensure those repository methods exist and accept the same parameters.
- Frontend forms should be updated to POST to the new endpoints. The view `maternal_health_record_form` is display-only and still renders the forms (so templates can continue using them for client-side rendering), but actual submission should use the new endpoints.
- If you want CSRF protection on AJAX JSON POSTs, ensure the frontend includes the CSRF token or switch to sessionless token-based auth if preferred.

Files changed
- Added: `maternal/api/*.py` (new API files as listed above) and `maternal/api/README_API_MIGRATION.md` (this file)
- Modified: `maternal/views.py` (removed prenatal_api fn; made `maternal_health_record_form` GET-only)
- Modified: `maternal/urls.py` (registered new endpoints)

If you want, I can:
- Add unit tests for each endpoint (basic validation + repository call mocking).
- Update frontend templates/JS to POST to the new endpoints and handle JSON responses.
