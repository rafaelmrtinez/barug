from typing import Any, Dict, Optional
import logging

from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.repositories.queries.maternal_health_record_queries import MaternalHealthRecordQueries
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException
from maternal.forms.form_utils import FormUtils

LOG = logging.getLogger(__name__)


class PrenatalFollowUpValidationException(Exception):
    def __init__(self, message: str = "Validation failed.", errors: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.errors = errors or {}


class ServiceExecutionException(Exception):
    pass


class PrenatalFollowUpService:
    """Service to validate and persist prenatal follow-up row entries.

    Encapsulates role-based validation rules and repository calls.
    """

    BASIC_INFO_PERMS = {"bhw", "barangay health worker"}
    FINDINGS_AND_NOTES_PERMS = {"midwife"}

    def __init__(self, repository: MaternalHealthRecordRepository, queries: Optional[MaternalHealthRecordQueries] = None):
        self.repository = repository
        self.queries = queries

    def _normalize_payload(self, payload: Dict[str, Any], prefix: Optional[str] = None) -> Dict[str, Any]:
        if not prefix:
            return payload
        norm = {}
        for k, v in payload.items():
            if k.startswith(prefix + "-"):
                norm[k.split('-', 1)[1]] = v
        # keep mhr_id, staff fields if present
        for key in ("mhr_id",):
            if key in payload:
                norm[key] = payload[key]
        return norm

    def validate(self, payload: Dict[str, Any], role: Optional[str] = None, prefix: Optional[str] = None, mhr_id: Optional[int] = None) -> Dict[str, Any]:
        # accept prefixed payload if needed
        data = self._normalize_payload(payload, prefix) if prefix else dict(payload)

        # ensure mhr_id is present (prefer explicit arg)
        mid = mhr_id or data.get('mhr_id')
        if not mid:
            raise PrenatalFollowUpValidationException('Missing maternal record id (mhr_id).', errors={'mhr_id': ['Missing maternal record id (mhr_id).']})

        role_norm = (role or '').strip().lower()

        # Sanitize findings/notes when allowed
        cleaned: Dict[str, Any] = {}
        for field_name, label in (('findings', 'Findings'), ('notes', 'Notes')):
            # If role is BHW, these are considered disabled (skip sanitization)
            if role_norm in self.BASIC_INFO_PERMS:
                # BHW fields are not required and are typically 'TBD' on the form
                cleaned[field_name] = data.get(field_name)
                continue

            value = data.get(field_name)
            if value is None:
                cleaned[field_name] = None
                continue
            normalized, err = FormUtils.sanitize_text(value, label)
            if err:
                raise PrenatalFollowUpValidationException(err, errors={field_name: [err]})
            cleaned[field_name] = normalized

        # If BHW, require basic measurement fields
        if role_norm in self.BASIC_INFO_PERMS:
            required_fields = [
                'aog_weeks', 'aog_days', 'wt_kg', 'bp_systolic', 'bp_diastolic'
            ]
            missing = []
            for fname in required_fields:
                val = data.get(fname)
                if val in (None, ''):
                    # use the field label name for message clarity
                    missing.append(fname)
            if missing:
                msg = (
                    "As a Barangay Health Worker, please fill out the following fields: "
                    + ", ".join(missing) + "."
                )
                raise PrenatalFollowUpValidationException(msg, errors={'__all__': [msg]})

        # For midwife or other roles: ensure findings/notes default to 'N/A' if both missing
        if role_norm not in self.BASIC_INFO_PERMS:
            if not cleaned.get('findings') and not cleaned.get('notes'):
                cleaned['findings'] = 'N/A'
                cleaned['notes'] = 'N/A'

        # Copy over numeric and simple fields with minimal coercion; rely on repository to validate types
        for simple in ('date', 'aog_weeks', 'aog_days', 'wt_kg', 'bp_systolic', 'bp_diastolic'):
            cleaned[simple] = data.get(simple)

        cleaned['mhr_id'] = int(mid)
        cleaned['role'] = role_norm

        return cleaned

    def save_followup(self, payload: Dict[str, Any], staff_id: int, role: Optional[str] = None, prefix: Optional[str] = None):
        if not self.repository:
            raise ServiceExecutionException('Repository not available for save operation.')

        # Validate (may raise PrenatalFollowUpValidationException)
        cleaned = self.validate(payload, role=role, prefix=prefix)
        mid = cleaned.get('mhr_id')

        try:
            role_norm = (role or '').strip().lower()
            
            if role_norm in self.BASIC_INFO_PERMS:
                res = self.repository.insert_anc_row_findings(
                    mhr_id=mid,
                    staff_id=staff_id,
                    aog_weeks=cleaned.get('aog_weeks'),
                    aog_days=cleaned.get('aog_days'),
                    weight=cleaned.get('wt_kg'),
                    bp_systolic=cleaned.get('bp_systolic'),
                    bp_diastolic=cleaned.get('bp_diastolic'),
                )
            else:
                # Midwife flow: update maternal anc row findings
                if not hasattr(self.repository, 'update_maternal_anc_row_findings'):
                    # caller/API will map this to 501
                    raise NotImplementedError('Midwife update not implemented.')

                # Check if midwife has already provided findings/notes for the latest record
                if self.queries and role_norm in self.FINDINGS_AND_NOTES_PERMS:
                    latest_anc_row = self.queries.get_latest_maternal_anc_row_by_mhr_id(mid)
                    if latest_anc_row:
                        # Check if findings and notes are already filled (not null/empty and not 'N/A')
                        existing_findings = latest_anc_row.get('leopolds_findings')
                        existing_notes = latest_anc_row.get('notes')
                        
                        # Consider 'N/A', None, empty string as not filled
                        findings_filled = existing_findings and existing_findings.strip() and existing_findings.strip().upper() != 'N/A'
                        notes_filled = existing_notes and existing_notes.strip() and existing_notes.strip().upper() != 'N/A'
                        
                        if findings_filled or notes_filled:
                            raise PrenatalFollowUpValidationException(
                                'Findings and/or notes have already been provided for the latest prenatal visit. Cannot update again.',
                                errors={'__all__': ['Findings and/or notes have already been provided for the latest prenatal visit. Cannot update again.']}
                            )

                # ensure defaults applied as in original API
                findings = cleaned.get('findings') or 'N/A'
                notes = cleaned.get('notes') or 'N/A'

                res = self.repository.update_maternal_anc_row_findings(
                    mhr_id=mid,
                    staff_id=staff_id,
                    findings=findings,
                    notes=notes,
                )
                self.repository.insert_maternal_visit_and_schedule_completion(
                    mhr_id=mid,
                    staff_id=staff_id,
                )

            return res
        except MaternalHealthRecordException:
            # propagate domain infra exceptions to API layer
            raise
        except NotImplementedError:
            raise
        except PrenatalFollowUpValidationException:
            # propagate validation exceptions
            raise
        except Exception:
            LOG.exception('Failed to persist prenatal follow-up for mhr_id=%s', mid)
            raise ServiceExecutionException('Failed to persist prenatal follow-up entry.')
