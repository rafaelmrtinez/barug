import json
import logging
from datetime import datetime

from django.http import JsonResponse, HttpRequest
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required

from authentication.guards import session_login_required, role_required
from dependency_injector.wiring import inject, Provide
from src.app.bootstrap.app_containers import AppContainer

from src.app.contracts.child_health_schedule_service import IChildHealthScheduleService
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.exceptions.child_health_record_exception import ChildHealthRecordException
from src.infra.repositories.child_health_record_repository import ChildHealthRecordRepository
from src.app.services.child_health_schedule_service import ChildHealthScheduleService
from src.app.transfer_objects.request.visit_schedule_request import VisitScheduleRequest

logger = logging.getLogger(__name__)

ALLOWED_ROLES = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")


@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*ALLOWED_ROLES), name="dispatch")
@method_decorator(csrf_required, name="dispatch")
class ChildHealthScheduleAPI(View):
    """Accept POST requests to create a child visit schedule.

    Expected JSON body:
      - child_record_id: int
      - schedule_date: string YYYY-MM-DD
      - schedule_time: string HH:MM or HH:MM:SS
      - visit_purpose: string (if 'other' then visit_purpose_other required)
      - visit_purpose_other: string (optional)
      - visit_notes: string (optional)

    The created_by (staff_id) is derived from session: request.session.get('auth', {}).get('staff_id')
    """

    @inject
    def post(self, request: HttpRequest, service: IChildHealthScheduleService = Provide[AppContainer.child_health_schedule_service], *args, **kwargs):
        """Create a child visit schedule.

        The repository is injected by the application container. If DI is not
        configured at runtime the provider will raise and we will surface a
        500 error the same way other API endpoints do.
        """
        # service is provided by DI container via the `service` parameter
        repo = ChildHealthRecordRepository(ConnectionAdapter())

        if service is None:
            # fallback: construct repository + service directly
            try:
                service = ChildHealthScheduleService(repo)
            except Exception:
                logger.exception('Error resolving child_health_schedule_service provider')
                return JsonResponse({'success': False, 'message': 'Unexpected server error.'}, status=500)

        try:
            payload = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'Invalid JSON body.'}, status=400)

        # Basic validation & sanitation
        errors = []
        child_record_id = payload.get('child_record_id')
        schedule_date = payload.get('schedule_date')
        schedule_time = payload.get('schedule_time')
        visit_purpose = (payload.get('visit_purpose') or '').strip()
        visit_purpose_other = (payload.get('visit_purpose_other') or '').strip()
        visit_notes = payload.get('visit_notes')

        # child_record_id
        try:
            child_record_id = int(child_record_id)
            if child_record_id <= 0:
                errors.append('child_record_id must be a positive integer')
        except Exception:
            errors.append('child_record_id is required and must be an integer')

        # schedule_date
        try:
            # accept YYYY-MM-DD
            dt_date = datetime.strptime(schedule_date, '%Y-%m-%d').date()
        except Exception:
            errors.append('schedule_date is required and must be YYYY-MM-DD')

        # schedule_time
        try:
            # accept HH:MM or HH:MM:SS
            dt_time = None
            if isinstance(schedule_time, str):
                try:
                    dt_time = datetime.strptime(schedule_time, '%H:%M').time()
                except Exception:
                    dt_time = datetime.strptime(schedule_time, '%H:%M:%S').time()
            else:
                raise ValueError()
        except Exception:
            errors.append('schedule_time is required and must be HH:MM or HH:MM:SS')

        if not visit_purpose:
            errors.append('visit_purpose is required')

        if visit_purpose.lower() == 'other' and not visit_purpose_other:
            errors.append('visit_purpose_other is required when visit_purpose is other')

        # notes length
        if visit_notes is not None:
            try:
                if len(str(visit_notes)) > 1000:
                    errors.append('visit_notes must be at most 1000 characters')
            except Exception:
                errors.append('visit_notes must be a string')

        if errors:
            return JsonResponse({'success': False, 'errors': errors}, status=400)

        # build DTO
        dto = VisitScheduleRequest(
            child_record_id=child_record_id,
            schedule_date=dt_date.isoformat(),
            schedule_time=dt_time.strftime('%H:%M:%S') if dt_time else schedule_time,
            visit_purpose=visit_purpose,
            visit_purpose_other=visit_purpose_other or None,
            visit_notes=visit_notes or None,
        )

        # created_by from session
        created_by = None
        try:
            created_by = request.session.get('auth', {}).get('staff_id')
            created_by = int(created_by)
        except Exception:
            created_by = None

        if not created_by:
            return JsonResponse({'success': False, 'message': 'Unable to determine authenticated staff id.'}, status=403)

        # delegate to service
        try:
            service = ChildHealthScheduleService(repo)
            result = service.create_visit_schedule(dto, created_by)
            return JsonResponse({'success': True, 'result': result}, status=201)
        except ChildHealthRecordException as e:
            logger.exception('Child health record error when creating visit schedule: %s', e)
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
        except Exception as e:
            logger.exception('Failed to create visit schedule: %s', e)
            return JsonResponse({'success': False, 'message': 'Failed to create visit schedule.'}, status=500)
