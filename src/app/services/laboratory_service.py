"""Laboratory service.

Provides a LaboratoryService class that builds a serializable payload from
cleaned paired test data and persists it using the repository. Form
validation must remain in the view layer and is not performed here.
"""
from typing import Any, Dict, List, Tuple
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)
from src.infra.utilities.supabase_storage_service import SupabaseStorageService
from src.app.contracts.laboratory_service import ILaboratoryService
from barug.utility.custom_date_time_util import DateAndTimeUtility
from datetime import date as _date


class LaboratoryTestException(Exception):
    """Raised when attempting to add/upload lab data for a test that already
    exists for the maternal record.

    Attributes:
        tests: optional list of lab_test_type_id values (or test names) that
            caused the conflict.
    """
    def __init__(self, message: str, tests: List[Any] = None):
        super().__init__(message)
        self.tests = tests or []


def _map_test_type_to_id(raw_test_type: Any) -> int:
    """Map a user-provided test_type (string or int-like) to the canonical
    lab_test_type_id. Returns None when mapping fails.
    """
    if raw_test_type is None:
        return None
    # if int-like, coerce
    try:
        return int(raw_test_type)
    except Exception:
        pass

    name_to_id = {
        'URINALYSIS': 1,
        'CBC': 2,
        'SGOT/SGPT': 3,
        'CREATININE SERUM': 4,
        'BUA/BUN': 5,
        'SYPHILIS': 6,
        'HIV TEST': 7,
        'HEPA B': 8,
        'BLOOD TYPING': 9,
        'OGCT 50G (24–28 WKS)': 10,
        'OGCT 50G (24-28 WKS)': 10,
        'OGTT 100G': 11,
    }

    try:
        s = str(raw_test_type).strip()
        s_lower = s.lower()
        mapped = name_to_id.get(s.upper())
        if mapped:
            return mapped

        # heuristics
        if 'ogct' in s_lower and 'ogtt' not in s_lower:
            return 10
        if 'ogtt' in s_lower:
            return 11
        if 'cbc' in s_lower:
            return 2
        if 'urinalysis' in s_lower or 'urine' in s_lower:
            return 1
        if 'sgot' in s_lower or 'sgpt' in s_lower:
            return 3
        if 'creatinine' in s_lower:
            return 4
        if 'bua' in s_lower or 'bun' in s_lower:
            return 5
        if 'syphilis' in s_lower or 'vdrl' in s_lower or 'rpr' in s_lower:
            return 6
        if 'hiv' in s_lower:
            return 7
        if 'hepa' in s_lower or 'hepatitis' in s_lower:
            return 8
        if ('blood' in s_lower and 'typing' in s_lower) or 'abo' in s_lower or 'rh' in s_lower:
            return 9

        # last resort: strip non-alphanumerics and re-check
        import re
        norm = re.sub(r'[^a-z0-9]', ' ', s_lower)
        if 'ogct' in norm:
            return 10
        if 'ogtt' in norm:
            return 11
    except Exception:
        logger.exception('Error while mapping test type: %s', raw_test_type)
    return None


class LaboratoryService(ILaboratoryService):
    """Service for building payloads and saving laboratory results.

    Initialize with repository, staff_id and record_id. Call `build_payload`
    to convert cleaned paired_tests into a JSON-friendly structure, then
    call `save` to persist it.
    """

    def __init__(self, repository, staff_id: Any, record_id: Any) -> None:
        self.repository = repository
        self.staff_id = staff_id
        self.record_id = record_id
        

    def build_payload(self, paired_tests) -> List[Dict[str, Any]]:
        """Convert cleaned paired_tests into the exact payload shape expected
        by the repository: a list of dicts with keys:

            - lab_test_type_id: int
            - date_tested: YYYY-MM-DD string (or None)
            - result_img_path: list of image paths/urls (may be empty)
            - result: string (the test result / description)

        paired_tests is expected to be the validated/cleaned data coming
        from the form layer (e.g., lab_form.cleaned_data.get('paired_tests')).
        The method will try to map a test_type name to the corresponding
        lab_test_type_id using the known mapping; if test_type is already an
        int-like value it will be used as-is.
        """

        serializable_pairs: List[Dict[str, Any]] = []
        for p in (paired_tests or []):
            # normalize and extract result (was previously called description)
            result = p.get('description')
            if isinstance(result, (bytes, bytearray)):
                result = result.decode('utf-8', errors='ignore')
            # handle decimal types etc.
            try:
                from decimal import Decimal as _Decimal
                if isinstance(result, _Decimal):
                    try:
                        result = float(result)
                    except Exception:
                        result = str(result)
            except Exception:
                pass

            # images are expected to be URLs/paths at this point (strings)
            imgs = p.get('images') or []
            imgs_normalized = [str(i) for i in imgs]

            # determine lab_test_type_id using helper
            raw_test_type = p.get('test_type')
            lab_test_type_id = _map_test_type_to_id(raw_test_type)

            # format date as YYYY-MM-DD
            date_val = p.get('date')
            date_tested = None
            if date_val:
                try:
                    # date_val may be a date/datetime or string
                    if hasattr(date_val, 'strftime'):
                        date_tested = date_val.strftime('%Y-%m-%d')
                    else:
                        # if it's a string already, attempt to parse common formats
                        # but prefer to leave provided YYYY-MM-DD strings as-is
                        date_tested = str(date_val)
                except Exception:
                    date_tested = None

            serializable_pairs.append({
                'lab_test_type_id': lab_test_type_id,
                'date_tested': date_tested,
                'result_img_path': imgs_normalized,
                'result': result,
            })
        return serializable_pairs

    def save(self, paired_tests) -> Dict[str, Any]:
        """Build payload from paired_tests and persist using repository.

        Returns a dict with keys:
            - success: bool
            - res: repository response
        """
        # Validate incoming paired_tests for required rules before any uploads
        # or DB checks. This ensures user-provided data is well-formed and
        # prevents unnecessary uploads.
        self._validate_paired_tests(paired_tests)

        # Orchestrator: validate intent first (do not upload files if some
        # tests already exist). We build the payload early so we can map
        # test_type -> lab_test_type_id and compare against existing ids.
        try:
            existing_ids = self._existing_lab_test_ids()
        except Exception:
            logger.exception('Failed to fetch existing lab test ids; will attempt to persist all uploaded pairs')
            existing_ids = set()

        # map incoming pairs to canonical payload (lab_test_type_id etc.)
        payload_preview = self.build_payload(paired_tests)

        # If any of the incoming tests already exist for this mhr, reject
        # the whole operation rather than allowing file uploads.
        conflicts = [p.get('lab_test_type_id') for p in payload_preview if p.get('lab_test_type_id') in existing_ids]
        if conflicts:
            logger.info('Attempt to add existing lab tests for mhr %s: %s', self.record_id, conflicts)
            raise LaboratoryTestException('Laboratory results for one or more tests already exist; cannot add or upload files.', tests=conflicts)

        # No conflicts — proceed with uploads
        uploaded_pairs = []
        uploaded_paths: List[str] = []

        # Step 1: upload files to Supabase (may raise). _upload_images now
        # attaches a private '_uploaded_paths' list to each pair so we can
        # selectively clean up only the files that correspond to persisted
        # records if a DB error occurs.
        try:
            uploaded_pairs, uploaded_paths = self._upload_images(paired_tests)
        except Exception:
            logger.exception('Failed while uploading images')
            # bubble up so callers (views) can return appropriate errors
            raise

        # Step 2: persist payload in DB; on failure attempt cleanup of the
        # files that were associated with the uploaded pairs.
        try:
            res = self._persist_payload(uploaded_pairs)
        except Exception:
            logger.exception('Error inserting maternal lab results; attempting to cleanup uploaded files for this operation')
            # gather any uploaded storage paths attached to the uploaded_pairs
            to_cleanup = []
            for up in uploaded_pairs:
                to_cleanup.extend(up.get('_uploaded_paths') or [])
            for path in to_cleanup:
                try:
                    SupabaseStorageService.remove_file(path, 'maternal')
                except Exception:
                    logger.exception('Failed to remove uploaded file during cleanup: %s', path)
            # re-raise so the caller/view sees the failure
            raise

        logger.info('Successfully persisted lab results for mhr=%s; repo_response=%s', self.record_id, bool(res))

        return {"success": bool(res), "res": res}

    def _upload_images(self, paired_tests) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Upload any file-like images to Supabase and return (uploaded_pairs, uploaded_paths).

        - uploaded_pairs: list of test dicts with the images replaced by public urls/paths
        - uploaded_paths: list of storage object paths (for cleanup)
        """
        uploaded_pairs: List[Dict[str, Any]] = []
        uploaded_paths: List[str] = []
        bucket = 'maternal'

        for p in (paired_tests or []):
            test_type = p.get('test_type') or 'unknown'
            images = p.get('images') or []
            # If there are no images for this pair, skip upload logic entirely.
            if not images:
                uploaded_pairs.append({
                    'test_type': test_type,
                    'date': p.get('date'),
                    'description': p.get('description'),
                    'images': [],
                    '_uploaded_paths': [],
                })
                continue
            uploaded_images: List[str] = []
            per_pair_paths: List[str] = []

            for img in images:
                # If the image is a file-like object (UploadedFile), upload it.
                if hasattr(img, 'read') or hasattr(img, 'content_type'):
                    orig_name = getattr(img, 'name', None) or f"{test_type}-{uuid.uuid4().hex}"
                    ts = datetime.utcnow().strftime('%Y%m%d%H%M%S')
                    filename = f"{ts}-{orig_name}"
                    destination_path = f"laboratory/{self.record_id}/{test_type}/{filename}"
                    try:
                        saved = SupabaseStorageService.save_file(img, destination_path, bucket)
                        public_url = saved.get('public_url') or saved.get('path')
                        uploaded_images.append(public_url)
                        saved_path = saved.get('path') or destination_path
                        uploaded_paths.append(saved_path)
                        per_pair_paths.append(saved_path)
                    except Exception:
                        # If any upload in this run fails, attempt to remove already-uploaded files
                        logger.exception('Failed to upload image for test %s', test_type)
                        for path in list(uploaded_paths):
                            try:
                                SupabaseStorageService.remove_file(path, bucket)
                            except Exception:
                                logger.exception('Failed to remove uploaded file during rollback: %s', path)
                        # re-raise the original upload exception
                        raise
                else:
                    # already a string (path or url) — keep as-is
                    uploaded_images.append(str(img))

            uploaded_pairs.append({
                'test_type': test_type,
                'date': p.get('date'),
                'description': p.get('description'),
                'images': uploaded_images,
                # internal: keep track of storage paths uploaded for this pair
                '_uploaded_paths': per_pair_paths,
            })

        return uploaded_pairs, uploaded_paths

    def _persist_payload(self, uploaded_pairs) -> Any:
        """Persist the uploaded_pairs to the repository and return the repo response.

        This method converts uploaded_pairs to a serializable payload and calls
        the repository layer. It raises on any repository error.
        """
        payload = self.build_payload(uploaded_pairs)
        return self.repository.insert_maternal_lab_results(
            mhr_id=self.record_id,
            staff_id=self.staff_id,
            lab_results=payload or [],
        )

    def _existing_lab_test_ids(self) -> set:
        """Return a set of lab_test_id ints that already exist for this record.

        Uses the repository method `fetch_lab_results_by_mhr_id` which must
        include `lab_test_id` in its result set.
        """
        try:
            rows = self.repository.fetch_lab_results_by_mhr_id(self.record_id) or []
        except Exception:
            logger.exception('Failed to query existing lab results for mhr %s', self.record_id)
            raise

        ids = set()
        for r in rows:
            lid = r.get('lab_test_id') or r.get('lab_test') or r.get('lab_test_type_id')
            if lid is None:
                continue
            try:
                ids.add(int(lid))
            except Exception:
                # ignore non-intable values
                continue

        return ids

    def _validate_paired_tests(self, paired_tests) -> None:
        """Validate paired_tests before processing.

        Rules enforced:
        - description/result must not be null/empty; accept 'N/A' or 'n/a' as explicit placeholders.
        - date must be present and valid; future dates are not allowed (Philippine timezone).

        Raises ValueError listing the problems when validation fails.
        """
        print(f'validate paired_tests: {paired_tests}')
        if not paired_tests:
            raise LaboratoryTestException('No laboratory tests provided. Please add a valid test.')
        
        errors: List[str] = []
        # current PH date
        current_date = DateAndTimeUtility.parse_date(DateAndTimeUtility.get_current_date())
        try:
            for idx, p in enumerate(paired_tests or []):
                test_type = p.get('test_type') or f'index_{idx}'

                # normalize and check description/result
                desc = p.get('description')
                if isinstance(desc, (bytes, bytearray)):
                    try:
                        desc = desc.decode('utf-8', errors='ignore')
                    except Exception:
                        desc = None

                if desc is None or (isinstance(desc, str) and desc.strip() == ''):
                    errors.append(f"{test_type}: result/description is required. If there is no further description, enter 'N/A'.")
                else:
                    # allow explicit N/A (case-insensitive)
                    if isinstance(desc, str) and desc.strip().lower() == 'n/a':
                        pass

                # validate date
                date_val = p.get('date')
                parsed_date = None
                if date_val is None:
                    errors.append(f"{test_type}: date is required and cannot be null.")
                    continue

                # if it's a date/datetime object, coerce to date
                if hasattr(date_val, 'strftime'):
                    try:
                        # datetime -> date
                        if isinstance(date_val, datetime):
                            parsed_date = date_val.date()
                        else:
                            parsed_date = date_val
                    except Exception:
                        parsed_date = None
                else:
                    # try parsing string using utility
                    parsed_date = DateAndTimeUtility.parse_date(date_val)

                if parsed_date is None:
                    errors.append(f"{test_type}: date is invalid or unrecognized ('{date_val}').")
                    continue

                if current_date and parsed_date > current_date:
                    errors.append(f"{test_type}: date {parsed_date} is in the future; future dates are not allowed.")
        except Exception:
            logger.exception('Unexpected error validating paired_tests')

        if errors:
            # raise a simple ValueError so callers can return a friendly message
            raise LaboratoryTestException('Validation errors: ' + '; '.join(errors))
