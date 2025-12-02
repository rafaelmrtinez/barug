from typing import Optional
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.repositories.queries.maternal_health_record_queries import MaternalHealthRecordQueries
from src.infra.repositories.queries.person_queries import PersonQuery
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException


class CreateMaternalHealthRecordService:
    """Service to create a maternal health record (thin wrapper around repository).

    This service exists to encapsulate any future business rules before
    delegating to the repository's `insert_maternal_health_record` function.
    """

    def __init__(
        self, 
        repository: MaternalHealthRecordRepository, 
        person_query: PersonQuery,
        mhr_query: MaternalHealthRecordQueries
        ):
        self.repository = repository
        self.person_query = person_query
        self.mhr_query = mhr_query
    
    def create_maternal_health_record(
        self,
        staff_id: int,
        person_id: int,
        husband_id: Optional[int],
        weight: Optional[float],
        height: Optional[float],
        bmi_status_id: Optional[int],
        is_transferred: bool = False):
        if not self.repository:
            raise MaternalHealthRecordException('Repository not available')

        # Basic argument normalization/validation may be added here.
        try:
            # If husband_id is not provided, attempt to resolve via PersonQuery
            if (husband_id is None or husband_id == '') and getattr(self, 'person_query', None):
                try:
                    spouse = self.person_query.get_husband_by_src_person_id(person_id)
                    if spouse and spouse.get('person_id'):
                        husband_id = int(spouse.get('person_id'))
                except Exception:
                    # best-effort: if lookup fails, continue with provided/None husband_id
                    husband_id = husband_id

            # Business rule: ensure the person does not already have an active MHR
            if getattr(self, 'mhr_query', None):
                try:
                    active = self.mhr_query.get_active_maternal_record_by_person_id(person_id)
                    if active:
                        raise MaternalHealthRecordException('This person has an active maternal health record')
                except MaternalHealthRecordException:
                    # propagate our domain exception
                    raise
                except Exception:
                    # best-effort: if mhr_query lookup fails, continue to attempt creation
                    pass

            res = self.repository.insert_maternal_health_record(
                staff_id=staff_id,
                person_id=person_id,
                husband_id=husband_id,
                weight=weight,
                height=height,
                bmi_status_id=bmi_status_id,
                is_transferred=is_transferred,
            )
            return res
        except MaternalHealthRecordException:
            raise
        except Exception:
            raise
