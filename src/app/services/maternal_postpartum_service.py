from datetime import date, time
from typing import Any, Dict, Optional

from maternal.repository import MaternalHealthRecordRepository
from maternal.exceptions.maternal_exceptions import MaternalHealthRecordException


def _to_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    s = str(val).strip().lower()
    return s in ('1', 'true', 't', 'yes', 'y', 'on')


def _sanitize_str(val: Any, max_len: Optional[int] = None) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    # basic sanitation: remove angle brackets to reduce trivial XSS risk in DB stored text
    s = s.replace('<', '').replace('>', '')
    if max_len is not None:
        return s[:max_len]
    return s


class MaternalPostpartumService:
    """Service to validate/sanitize postpartum payloads and persist via repository.

    Responsibilities:
      - validate and coerce incoming payload fields
      - raise MaternalHealthRecordException for business/validation errors
      - delegate persistence to the repository
    """

    def __init__(self, repository: MaternalHealthRecordRepository):
        self.repo = repository

    def insert_postpartum_record(self, payload: Dict[str, Any], added_by_id: int, attended_by_role_name: Optional[str] = None):
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
                attended_by_id = int(added_by_id)
            else:
                attended_by_id = int(attended_by_id)
        except Exception:
            raise MaternalHealthRecordException('Invalid attended_by_id.')

        # place_of_delivery_id optional int
        pod = data.get('place_of_delivery_id')
        try:
            place_of_delivery_id = int(pod) if pod not in (None, '', []) else None
        except Exception:
            raise MaternalHealthRecordException('Invalid place_of_delivery_id.')

        # outcome: optional short text
        outcome = _sanitize_str(data.get('outcome'), max_len=200)

        # booleans
        iron = _to_bool(data.get('iron_supplementation'))
        vit_a = _to_bool(data.get('vit_a_supplementation'))
        mebendazole = _to_bool(data.get('mebendazole_given'))

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

        # call repository
        try:
            return self.repo.insert_postpartum_record_bhw(
                p_added_by_id=added_by_id,
                p_maternal_record_id=mhr_id,
                p_date_of_delivery=parsed_date,
                p_time_of_delivery=parsed_time,
                p_attended_by_id=attended_by_id,
                p_attended_by_rolename=_sanitize_str(attended_by_role_name, max_len=100),
                p_place_of_delivery_id=place_of_delivery_id,
                p_outcome=outcome,
                p_iron_supplementation=iron,
                p_vit_a_supplementation=vit_a,
                p_mebendazole_given=mebendazole,
                p_lochial_discharges_baseline=lochial,
                p_pads_per_day_baseline=pads_int,
            )
        except MaternalHealthRecordException:
            raise
        except Exception as e:
            # wrap unexpected exceptions for caller convenience
            raise
