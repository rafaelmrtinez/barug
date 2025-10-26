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
from maternal.supa.supabase_storage_service import SupabaseStorageService


class LaboratoryService:
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

        # mapping of known lab test names (case-insensitive) to their ids
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

            # determine lab_test_type_id
            raw_test_type = p.get('test_type')
            lab_test_type_id = None
            if raw_test_type is None:
                lab_test_type_id = None
            else:
                # if it's already an int-like value, coerce
                try:
                    lab_test_type_id = int(raw_test_type)
                except Exception:
                    # normalize string and try several heuristic matches
                    try:
                        s = str(raw_test_type).strip()
                        s_lower = s.lower()

                        # direct name map (case-insensitive)
                        mapped = name_to_id.get(s.upper())
                        if mapped:
                            lab_test_type_id = mapped
                        else:
                            # common synonyms / slug forms
                            if 'ogct' in s_lower and 'ogtt' not in s_lower:
                                lab_test_type_id = 10
                            elif 'ogtt' in s_lower:
                                lab_test_type_id = 11
                            elif 'cbc' in s_lower:
                                lab_test_type_id = 2
                            elif 'urinalysis' in s_lower or 'urine' in s_lower:
                                lab_test_type_id = 1
                            elif 'sgot' in s_lower or 'sgpt' in s_lower:
                                lab_test_type_id = 3
                            elif 'creatinine' in s_lower:
                                lab_test_type_id = 4
                            elif 'bua' in s_lower or 'bun' in s_lower:
                                lab_test_type_id = 5
                            elif 'syphilis' in s_lower or 'vdrl' in s_lower or 'rpr' in s_lower:
                                lab_test_type_id = 6
                            elif 'hiv' in s_lower:
                                lab_test_type_id = 7
                            elif 'hepa' in s_lower or 'hepatitis' in s_lower:
                                lab_test_type_id = 8
                            elif 'blood' in s_lower and 'typing' in s_lower or 'abo' in s_lower or 'rh' in s_lower:
                                lab_test_type_id = 9
                            else:
                                # as a last resort, try to match by stripping non-alphanumerics
                                import re
                                norm = re.sub(r'[^a-z0-9]', ' ', s_lower)
                                if 'ogct' in norm:
                                    lab_test_type_id = 10
                                elif 'ogtt' in norm:
                                    lab_test_type_id = 11
                                else:
                                    lab_test_type_id = None
                        if lab_test_type_id is None:
                            logger.warning('Could not resolve lab_test_type_id for raw test_type: %s', raw_test_type)
                    except Exception:
                        lab_test_type_id = None

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
        # Orchestrator: upload images then persist payload. Both steps are
        # delegated to small, focused helper methods to keep flow readable.
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

        # Step 1.5: check existing lab_test_ids for this maternal record and
        # decide which uploaded pairs actually need DB persistence. If a
        # matching lab_test_id is already present we will skip persistence for
        # that test and only keep the uploaded images.
        try:
            existing_ids = self._existing_lab_test_ids()
        except Exception:
            # If we cannot fetch existing ids, be conservative and proceed
            # with persistence for all uploaded pairs (so we don't accidentally
            # overwrite user's intent). Do not fail here.
            logger.exception('Failed to fetch existing lab test ids; will attempt to persist all uploaded pairs')
            existing_ids = set()
        else:
            logger.debug('Existing lab_test_ids for mhr %s: %s', self.record_id, existing_ids)

        # Build the canonical payload and split into to_persist vs skipped
        payload = self.build_payload(uploaded_pairs)
        to_persist = []
        persist_uploaded_paths: List[str] = []
        skipped_info = []

        for idx, entry in enumerate(payload):
            lab_test_type_id = entry.get('lab_test_type_id')
            if lab_test_type_id is not None and lab_test_type_id in existing_ids:
                # skip persistence for this test; record advice for caller
                skipped_info.append({
                    'lab_test_type_id': lab_test_type_id,
                    'note': 'existing_record_found'
                })
                logger.info('Skipping DB persistence for lab_test_type_id=%s (existing record found) on mhr=%s', lab_test_type_id, self.record_id)
                # nothing else to do for this pair (images were already uploaded)
                continue
            # include in persistence payload
            to_persist.append(entry)
            logger.debug('Will persist lab_test_type_id=%s for mhr=%s', lab_test_type_id, self.record_id)
            # gather uploaded file paths tied to this pair for cleanup if needed
            per_paths = uploaded_pairs[idx].get('_uploaded_paths') or []
            persist_uploaded_paths.extend(per_paths)

        # If nothing to persist, we're done -- images uploaded only
        if not to_persist:
            logger.info('No new lab tests to persist for mhr=%s; uploaded images only. skipped=%s', self.record_id, skipped_info)
            return {"success": True, "res": None, "skipped": skipped_info}

        # Step 2: persist payload in DB; on failure attempt cleanup of only
        # the files that were associated with the persisted payload.
        try:
            logger.info('Persisting %d new lab test(s) for mhr=%s: %s', len(to_persist), self.record_id, [p.get('lab_test_type_id') for p in to_persist])
            res = self.repository.insert_maternal_lab_results(
                mhr_id=self.record_id,
                staff_id=self.staff_id,
                lab_results=to_persist or None,
            )
        except Exception:
            logger.exception('Error inserting maternal lab results; attempting to cleanup uploaded files for persisted items')
            for path in persist_uploaded_paths:
                try:
                    SupabaseStorageService.remove_file(path, 'maternal')
                except Exception:
                    logger.exception('Failed to remove uploaded file during cleanup: %s', path)
            # re-raise so the caller/view sees the failure
            raise

        logger.info('Successfully persisted lab results for mhr=%s; repo_response=%s', self.record_id, bool(res))

        return {"success": bool(res), "res": res, "skipped": skipped_info}

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
            lab_results=payload or None,
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
