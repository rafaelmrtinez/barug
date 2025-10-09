from dataclasses import dataclass

from src.app.transfer_objects.response.current_maternal_record_response import CurrentMaternalRecordResponse
from src.app.transfer_objects.response.maternal_record_basic_history_response import MaternalRecordBasicHistoryResponse
from src.app.transfer_objects.response.previous_maternal_record_response import PreviousMaternalRecordResponse

@dataclass
class MaternalRecordResponse:
    family_id: int | None = None
    current_materrnal_record: CurrentMaternalRecordResponse | None = None
    previous_maternal_records: PreviousMaternalRecordResponse | None = None
    record_history: list[MaternalRecordBasicHistoryResponse] | None = None