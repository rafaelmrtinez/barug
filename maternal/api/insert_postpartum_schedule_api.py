import json
from datetime import date, time

from django.http import JsonResponse, HttpRequest
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required

from authentication.guards import session_login_required, role_required
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException
from src.app.services.maternal_schedule_service import MaternalScheduleService

ALLOWED_ROLES = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")


@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*ALLOWED_ROLES), name="dispatch")
@method_decorator(csrf_required, name="dispatch")
class PostpartumScheduleAPI(View):
    """API to insert a postpartum schedule.

    Expected JSON body:
      { "mhr_id": int, "schedule_date": "YYYY-MM-DD", "schedule_time": "HH:MM", "visit": str, "purpose": str }
    staff_id comes from session: request.session['auth']['staff_id']
    """

    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid JSON payload.'}, status=400)

        mhr_id = payload.get('mhr_id')
        sched_date = payload.get('schedule_date')
        sched_time = payload.get('schedule_time')
        visit = (payload.get('visit') or '').strip()
        purpose = (payload.get('purpose') or '').strip()

        if mhr_id is None or sched_date is None or sched_time is None or not visit or not purpose:
            return JsonResponse({'success': False, 'message': 'Missing required fields.'}, status=400)

        try:
            mhr_id = int(mhr_id)
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'message': 'mhr_id must be integer.'}, status=400)

        # parse/validate date and time
        try:
            parsed_date = date.fromisoformat(sched_date)
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid schedule_date. Use YYYY-MM-DD.'}, status=400)

        try:
            parts = sched_time.split(':')
            if len(parts) >= 2:
                hh = int(parts[0]); mm = int(parts[1]); ss = int(parts[2]) if len(parts) > 2 else 0
                parsed_time = time(hh, mm, ss)
            else:
                raise ValueError()
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid schedule_time. Use HH:MM.'}, status=400)

        staff_id = request.session.get('auth', {}).get('staff_id')
        try:
            staff_id = int(staff_id)
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'message': 'Invalid staff id in session.'}, status=400)

        repo = MaternalHealthRecordRepository(ConnectionAdapter())
        service = MaternalScheduleService(repo)

        try:
            res = service.schedule_postpartum(mhr_id, parsed_date, parsed_time, staff_id, visit, purpose)
        except MaternalHealthRecordException as e:
            return JsonResponse({'success': False, 'message': e.message or str(e)}, status=400)
        except Exception as e:
            import logging
            logging.exception('Unexpected error scheduling postpartum visit')
            return JsonResponse({'success': False, 'message': 'Unexpected server error.'}, status=500)

        if not res:
            return JsonResponse({'success': False, 'message': 'Failed to save postpartum schedule.'}, status=500)

        return JsonResponse({'success': True, 'message': 'Postpartum schedule saved.', 'result': res})
