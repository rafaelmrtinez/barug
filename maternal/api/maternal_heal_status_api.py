import json

from django.http import JsonResponse, HttpRequest
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required

from authentication.guards import session_login_required, role_required
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException
from src.app.services.maternal_status_service import MaternalRecordStatusService
from dependency_injector.wiring import inject, Provide
from barug.containers import app

LOGGER_ALLOWED_ROLES = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")


@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*LOGGER_ALLOWED_ROLES), name="dispatch")
@method_decorator(csrf_required, name="dispatch")
class MaternalHealthRecordStatusUpdateAPI(View):
    """API endpoint v1 to update maternal health record status.

    POST JSON body expected:
      { "mhr_id": int, "status_id": int }

    The staff_id is taken from the session (`request.session['auth']['staff_id']`).
    """

    @inject
    def post(self, request: HttpRequest, service: MaternalRecordStatusService = Provide[app.maternal_status_service], *args, **kwargs) -> JsonResponse:
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid JSON payload.'}, status=400)

        mhr_id = payload.get('mhr_id')
        status_id = payload.get('status_id')

        if mhr_id is None or status_id is None:
            return JsonResponse({'success': False, 'message': 'Missing required fields: mhr_id and status_id are required.'}, status=400)

        # sanitize/coerce to ints
        try:
            mhr_id = int(mhr_id)
            status_id = int(status_id)
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'message': 'mhr_id and status_id must be integers.'}, status=400)

        staff_id = request.session.get('auth', {}).get('staff_id')
        
        if not staff_id:
            return JsonResponse({'success': False, 'message': 'Unauthenticated staff id.'}, status=401)

        try:
            staff_id = int(staff_id)
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'message': 'Invalid staff id in session.'}, status=400)

        # Use injected service when available; fallback to container or local construction
        try:
            need_resolve = not service or not hasattr(service, 'is_valid_status')
        except Exception:
            need_resolve = True

        if need_resolve:
            try:
                service = app.maternal_status_service()
            except Exception:
                repo = MaternalHealthRecordRepository(ConnectionAdapter())
                service = MaternalRecordStatusService(repo)

        # validate status id against allowed set
        if not service.is_valid_status(status_id):
            return JsonResponse({'success': False, 'message': 'Invalid status id.'}, status=400)

        try:
            res = service.update_status(mhr_id, status_id, staff_id)
        except MaternalHealthRecordException as e:
            return JsonResponse({'success': False, 'message': e.message or str(e)}, status=400)
        except ValueError as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=404)
        except Exception as e:
            import logging
            logging.exception('Unexpected error updating MHR status')
            return JsonResponse({'success': False, 'message': 'Unexpected server error.'}, status=500)

        # success
        return JsonResponse({'success': True, 'message': 'Maternal record status updated.', 'result': res})
