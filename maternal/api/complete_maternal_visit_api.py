import json

from django.http import JsonResponse, HttpRequest
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required

from authentication.guards import session_login_required, role_required
from src.infra.database.connection_adapter import ConnectionAdapter
from maternal.repository import MaternalHealthRecordRepository
from maternal.exceptions.maternal_exceptions import MaternalHealthRecordException


ALLOWED_ROLES = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")


@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*ALLOWED_ROLES), name="dispatch")
@method_decorator(csrf_required, name="dispatch")
class CompleteMaternalVisitAPI(View):
    """API to complete a maternal visit schedule by invoking repository logic.

    POST JSON body expected: { "mhr_id": int }
    staff_id is taken from session (request.session['auth']['staff_id']).
    """

    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid JSON payload.'}, status=400)

        mhr_id = payload.get('mhr_id')
        if mhr_id is None:
            return JsonResponse({'success': False, 'message': 'Missing required field: mhr_id.'}, status=400)

        try:
            mhr_id = int(mhr_id)
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'message': 'mhr_id must be an integer.'}, status=400)

        staff_id = request.session.get('auth', {}).get('staff_id')
        # if not staff_id:
        #     return JsonResponse({'success': False, 'message': 'Unauthenticated staff id.'}, status=401)

        try:
            staff_id = int(staff_id)
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'message': 'Invalid staff id in session.'}, status=400)

        repo = MaternalHealthRecordRepository(ConnectionAdapter())

        try:
            res = repo.insert_maternal_visit_and_schedule_completion(mhr_id, staff_id)
        except MaternalHealthRecordException as e:
            return JsonResponse({'success': False, 'message': e.message or str(e)}, status=400)
        except Exception as e:
            import logging
            logging.exception('Unexpected error completing maternal visit')
            return JsonResponse({'success': False, 'message': 'Unexpected server error.'}, status=500)

        if not res:
            return JsonResponse({'success': False, 'message': 'Failed to complete maternal visit.'}, status=500)

        return JsonResponse({'success': True, 'message': 'Maternal visit completed.', 'result': res})
