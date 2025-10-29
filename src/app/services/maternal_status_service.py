"""Application service for maternal health record status updates.

This service performs coordination between repository calls and domain
validation. It belongs to the "application" layer (or service layer) and may be
used by controllers / API endpoints.
"""
from typing import Optional

from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException
from src.domain.services.maternal_status_domain_service import MaternalStatusDomainService, MaternalStatusDomainException


class MaternalRecordStatusService:

    def __init__(self, repository: MaternalHealthRecordRepository):
        self.repo = repository

    def is_valid_status(self, status_id: int) -> bool:
        """Return True if status_id exists in the record_status table."""
        rows = self.repo.fetch_all_mhr_completion_status() or []
        ids = set()
        for r in rows:
            if isinstance(r, dict):
                try:
                    ids.add(int(r.get('record_status_id')))
                except Exception:
                    continue
            elif isinstance(r, (list, tuple)):
                try:
                    ids.add(int(r[0]))
                except Exception:
                    continue
        return int(status_id) in ids

    def update_status(self, mhr_id: int, status_id: int, staff_id: int):
        # ensure the MHR exists and extract current status id/name
        existing = self.repo.fetch_maternal_health_record_status_by_mhr_id(mhr_id)
        if existing is None:
            raise ValueError("Maternal health record not found")

        existing_status_id = None
        existing_status_name = None
        if isinstance(existing, dict):
            existing_status_id = existing.get('record_status_id')
            existing_status_name = existing.get('record_status_name')
        elif isinstance(existing, (list, tuple)):
            try:
                existing_status_id = existing[0]
            except Exception:
                existing_status_id = None
            try:
                existing_status_name = existing[1]
            except Exception:
                existing_status_name = None

        # normalize incoming id and build id->name map for statuses
        try:
            incoming_id = int(status_id)
        except Exception:
            raise ValueError("Invalid status id")

        status_rows = self.repo.fetch_all_mhr_completion_status() or []
        id_name_map = {}
        for r in status_rows:
            if isinstance(r, dict):
                try:
                    id_name_map[int(r.get('record_status_id'))] = r.get('record_status_name')
                except Exception:
                    continue
            elif isinstance(r, (list, tuple)):
                try:
                    id_name_map[int(r[0])] = r[1] if len(r) > 1 else None
                except Exception:
                    continue

        incoming_name = id_name_map.get(incoming_id)

        # Delegate domain validations (including null/new-equals-existing checks)
        try:
            MaternalStatusDomainService.validate_status_transition(
                existing_status_id, incoming_id, existing_status_name
            )
        except MaternalStatusDomainException as e:
            # Re-raise as ValueError to keep application-level exception shape
            raise ValueError(str(e)) from e

        # 3-5. If incoming status is ONGOING, ensure this maternal record is the latest
        if incoming_name and isinstance(incoming_name, str) and incoming_name.strip().upper() == 'ONGOING':
            # fetch person id for the given maternal record
            person_id = self.repo.fetch_person_id_by_maternal_record_id(mhr_id)
            if person_id is None:
                raise ValueError("Person not found for maternal health record")

            latest_mhr_id = self.repo.fetch_latest_maternal_health_record_id_by_person_id(person_id)
            # if there is a latest record and it's not this one, disallow reverting to ONGOING
            if latest_mhr_id is not None and int(latest_mhr_id) != int(mhr_id):
                raise ValueError("Archived maternal status can not be opened once another maternal health record is started")

        # 3-5. If incoming status is ONGOING, ensure this maternal record is the latest
        if incoming_name and isinstance(incoming_name, str) and incoming_name.strip().upper() == 'ONGOING':
            # fetch person id for the given maternal record
            person_id = self.repo.fetch_person_id_by_maternal_record_id(mhr_id)
            if person_id is None:
                raise ValueError("Person not found for maternal health record")

            latest_mhr_id = self.repo.fetch_latest_maternal_health_record_id_by_person_id(person_id)
            # if there is a latest record and it's not this one, disallow reverting to ONGOING
            if latest_mhr_id is not None and int(latest_mhr_id) != int(mhr_id):
                raise ValueError("Archived maternal status can not be opened once another maternal health record is started")

        # perform update using repository
        try:
            return self.repo.update_maternal_record_status(mhr_id, incoming_id, staff_id)
        except MaternalHealthRecordException:
            # re-raise repository/domain-specific exceptions to the caller
            raise
