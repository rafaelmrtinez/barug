from datetime import date, time, datetime
from typing import Any, Dict, Optional

from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.app.contracts.maternal_postpartum_service import IMaternalPostpartumService
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException



def _sanitize_str(val: Any, max_len: Optional[int] = None) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    # basic sanitation: remove angle brackets to reduce trivial XSS risk in DB stored text
    s = s.replace('<', '').replace('>', '')
    if max_len is not None:
        return s[:max_len]
    return s


class MaternalPostpartumService(IMaternalPostpartumService):
    """Service to validate/sanitize postpartum payloads and persist via repository.

    Responsibilities:
      - validate and coerce incoming payload fields
      - raise MaternalHealthRecordException for business/validation errors
      - delegate persistence to the repository
    """

    def __init__(self, repository: MaternalHealthRecordRepository):
        self.repo = repository

    def insert_postpartum_record(self, payload: Dict[str, Any], added_by_id: int):
        """Validate and insert a postpartum record.

        Returns repository result on success or raises MaternalHealthRecordException on validation/business errors.
        """
        data = payload or {}

        # maternal_record_id (required, int)
        mhr_id = data.get('maternal_record_id')
        try:
            mhr_id = int(mhr_id)
            if mhr_id <= 0:
                raise ValueError()
        except Exception:
            raise MaternalHealthRecordException('Invalid maternal_record_id.')

        # date_of_delivery (required) - expect ISO YYYY-MM-DD or date object
        dod = data.get('date_of_delivery')
        try:
            if isinstance(dod, date):
                parsed_date = dod
            else:
                parsed_date = date.fromisoformat(str(dod))
        except Exception:
            raise MaternalHealthRecordException('Invalid date_of_delivery. Use YYYY-MM-DD.')

        # time_of_delivery (required) - expect HH:MM or HH:MM:SS
        tod = data.get('time_of_delivery')
        try:
            if isinstance(tod, time):
                parsed_time = tod
            else:
                # time.fromisoformat exists but to be permissive parse manually
                parts = str(tod).split(':')
                if len(parts) < 2:
                    raise ValueError()
                hh = int(parts[0]); mm = int(parts[1]); ss = int(parts[2]) if len(parts) > 2 else 0
                parsed_time = time(hh, mm, ss)
        except Exception:
            raise MaternalHealthRecordException('Invalid time_of_delivery. Use HH:MM or HH:MM:SS.')

        # attended_by_id: prefer payload value, fallback to added_by_id
        attended_by_id = data.get('attended_by_id')
        try:
            if attended_by_id is None or str(attended_by_id).strip() == '':
                raise ValueError()
            else:
                attended_by_id = int(attended_by_id)
        except Exception:
            raise MaternalHealthRecordException('Only midwife are allowed to attend a patient.')

        # place_of_delivery_id optional int
        pod = data.get('place_of_delivery_id')
        try:
            place_of_delivery_id = int(pod) if pod not in (None, '', []) else None
        except Exception:
            raise MaternalHealthRecordException('Invalid place_of_delivery_id.')

        # outcome: optional short text
        outcome = _sanitize_str(data.get('outcome'), max_len=200)

        # Parse supplement date fields
        # Iron supplementation is no longer accepted from the UI payload. We
        # intentionally do not trust a user-provided iron flag and do not expose
        # it as an incoming parameter. The repository DB function still expects
        # a boolean value in the call; pass False here to keep existing DB
        # behavior without trusting UI input.
        iron = False

        def _parse_optional_date_field(val: Any, name: str):
            if val is None or str(val).strip() == '':
                return None
            try:
                if isinstance(val, date):
                    return val
                return date.fromisoformat(str(val))
            except Exception:
                raise MaternalHealthRecordException(f'Invalid {name}. Use YYYY-MM-DD.')

        def _parse_optional_datetime_field(val: Any, name: str):
            if val is None or str(val).strip() == '':
                return None
            try:
                if isinstance(val, datetime):
                    return val
                # Accept both 'YYYY-MM-DDTHH:MM' (from datetime-local) and full ISO
                return datetime.fromisoformat(str(val))
            except Exception:
                raise MaternalHealthRecordException(f'Invalid {name}. Use ISO datetime format (YYYY-MM-DDTHH:MM).')

        vit_a = _parse_optional_date_field(data.get('vit_a_supplementation'), 'vit_a_supplementation')
        mebendazole = _parse_optional_date_field(data.get('mebendazole_given'), 'mebendazole_given')
        bf_initiated_at = _parse_optional_datetime_field(data.get('bf_initiated_at'), 'bf_initiated_at')

        # longer text
        lochial = _sanitize_str(data.get('lochial_discharges_baseline'), max_len=500)

        # pads per day baseline optional int
        pads = data.get('pads_per_day_baseline')
        try:
            pads_int = int(pads) if pads not in (None, '', []) else None
            if pads_int is not None and pads_int < 0:
                raise ValueError()
        except Exception:
            raise MaternalHealthRecordException('Invalid pads_per_day_baseline.')

        # Domain rule: do not allow creating a postpartum record when there is
        # already an existing postpartum record for this maternal health record.
        # Fetch the latest postpartum record (if any) and block creation.
        try:
            existing_record = self.repo.fetch_postpartum_record_by_mhr_id(mhr_id)
        except Exception:
            # If repository check fails unexpectedly, raise a friendly error.
            raise MaternalHealthRecordException('Unable to validate existing postpartum records. Please try again.')

        if existing_record:
            # There is already at least one postpartum record for this MHR.
            raise MaternalHealthRecordException('A postpartum record already exists for this maternal health record. Duplicate postpartum records are not allowed.')

        # Additionally, keep the existing check that prevents creating a postpartum
        # record when there is an active/pending postpartum schedule.
        try:
            latest_pp_status = self.repo.fetch_latest_postpartum_status_by_mhr_id(mhr_id)
        except Exception:
            # If repository check fails unexpectedly, raise a friendly error.
            raise MaternalHealthRecordException('Unable to validate existing postpartum status. Please try again.')

        if latest_pp_status and int(latest_pp_status.get('status_id') or 0) == 1:
            # Status 1 == PENDING / active
            raise MaternalHealthRecordException('A pending postpartum schedule already exists. Complete or cancel it before adding a new postpartum record.')

        # Resolve the attended_by value (we expect the payload value to be a
        # person_id coming from the form ChoiceField). Query the staff table to
        # obtain the staff row and ensure the role is MIDWIFE (role_id == 11)
        # and that the staff account is active. We then pass the staff_id and
        # role_name returned by the DB function to the insert call.
        try:
            staff_rows = self.repo.fetch_staff_by_person_id(attended_by_id, role_id=11)
        except Exception:
            raise MaternalHealthRecordException('Unable to validate the selected attendant. Please try again.')

        if not staff_rows:
            raise MaternalHealthRecordException('Selected attendant is not a recognized midwife. Please choose a midwife from the list.')

        # Loop through returned rows and find one with active acc_status_id == 1.
        active_row = None
        for r in staff_rows:
            try:
                if int(r.get('acc_status_id') or 0) == 1:
                    active_row = r
                    break
            except Exception:
                # skip malformed rows
                continue

        if not active_row:
            # We found staff rows for the person and role, but none are active.
            # This defends against DB inconsistencies where duplicates exist
            # with varying statuses. Provide a friendly error for users.
            raise MaternalHealthRecordException('Selected attendant appears to be a midwife but is not currently active. Please choose an active midwife.')

        # Use the staff_id (DB PK) when calling repository insert, and use the
        # role_name returned by the DB for the attended_by_rolename parameter.
        attended_by_staff_id = int(active_row.get('staff_id'))
        attended_by_rolename = active_row.get('role_name')

        # call repository to persist the postpartum record
        try:
            return self.repo.insert_postpartum_record_bhw(
                p_added_by_id=added_by_id,
                p_maternal_record_id=mhr_id,
                p_date_of_delivery=parsed_date,
                p_time_of_delivery=parsed_time,
                p_attended_by_id=attended_by_staff_id,
                p_attended_by_rolename=attended_by_rolename,
                p_place_of_delivery_id=place_of_delivery_id,
                p_outcome=outcome,
                p_vit_a_supplementation=vit_a,
                p_mebendazole_given=mebendazole,
                p_lochial_discharges_baseline=lochial,
                p_pads_per_day_baseline=pads_int,
                p_bf_initiated_at=bf_initiated_at,
            )
        except MaternalHealthRecordException:
            raise
        except Exception as e:
            # wrap unexpected exceptions for caller convenience
            raise
