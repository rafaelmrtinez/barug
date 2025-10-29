# maternal/utils.py (new small helper)
from django.http import JsonResponse
from django.shortcuts import redirect

from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository

class FormLockUtility:

    LOCKED_NAMES = ('COMPLETE', 'INCOMPLETE')

    @staticmethod
    def is_mhr_locked(repo: MaternalHealthRecordRepository, mhr_id) -> bool:
        row = repo.fetch_maternal_health_record_status_by_mhr_id(mhr_id) or {}
        return (row.get('record_status_name') or "").upper() in FormLockUtility.LOCKED_NAMES

    @staticmethod
    def deny_if_locked(request, repo: MaternalHealthRecordRepository, mhr_id, api=False):
        if FormLockUtility.is_mhr_locked(repo, mhr_id):
            if api:
                return JsonResponse({'success': False, 'message': 'Record is locked. No further edits allowed.'}, status=403)
            # for regular form POSTs, show message and redirect back
            from django.contrib import messages
            messages.warning(request, 'This maternal health record is locked. Edits are not allowed.')
            return redirect(request.path)  # or to the form page
        return None