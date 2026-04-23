import json
import logging
from django.http import JsonResponse, HttpRequest
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required

from authentication.guards import session_login_required, role_required
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException

logger = logging.getLogger(__name__)

BHW_ROLES = ("Barangay Health Worker", "bhw")


@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*BHW_ROLES), name="dispatch")
@method_decorator(csrf_required, name="dispatch")
class PostpartumVisitBHWAPI(View):
    """API endpoint for Barangay Health Worker to create/reuse today's postpartum visit row.

    Expects JSON with at least `maternal_record_id` and optional measurements:
      - lochial_discharge (text)
      - bp_systolic (int)
      - bp_diastolic (int)
      - feeding_type_id (int)
      - notes (text)

    Returns JSON { success: bool, visit_id: int } on success.
    """

    def post(self, request: HttpRequest, *args, **kwargs):
        if not (request.content_type and 'application/json' in request.content_type):
            return JsonResponse({'success': False, 'message': 'JSON required.'}, status=400)

        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid JSON payload.'}, status=400)

        mhr_id = payload.get('maternal_record_id') or payload.get('mhr_id')
        if not mhr_id:
            return JsonResponse({'success': False, 'message': 'Missing maternal record id (mhr_id).'}, status=400)

        staff_id = request.session.get('auth', {}).get('staff_id')

        # coerce numeric values
        try:
            bp_systolic = int(payload.get('bp_systolic')) if payload.get('bp_systolic') is not None else None
        except Exception:
            bp_systolic = None
        try:
            bp_diastolic = int(payload.get('bp_diastolic')) if payload.get('bp_diastolic') is not None else None
        except Exception:
            bp_diastolic = None
        try:
            feeding_type_id = int(payload.get('feeding_type_id')) if payload.get('feeding_type_id') is not None else None
        except Exception:
            feeding_type_id = None

        lochial = payload.get('lochial_discharge')
        notes = payload.get('notes')

        repo = MaternalHealthRecordRepository(ConnectionAdapter())

        try:
            visit_id = repo.get_or_create_today_postpartum_visit(
                p_maternal_record_id=mhr_id,
                p_staff_id=staff_id,
                p_lochial_discharges=lochial,
                p_bp_systolic=bp_systolic,
                p_bp_diastolic=bp_diastolic,
                p_feeding_type_id=feeding_type_id,
            )

            if not visit_id:
                return JsonResponse({'success': False, 'message': 'Failed to create or fetch postpartum visit.'}, status=500)

            # Optionally return notes or other values
            return JsonResponse({'success': True, 'message': 'Postpartum visit saved.', 'visit_id': visit_id})

        except MaternalHealthRecordException as e:
            return JsonResponse({'success': False, 'message': e.message or str(e)}, status=400)
        except Exception:
            logger.exception('Unexpected error in PostpartumVisitBHWAPI')
            return JsonResponse({'success': False, 'message': 'Unexpected server error.'}, status=500)
