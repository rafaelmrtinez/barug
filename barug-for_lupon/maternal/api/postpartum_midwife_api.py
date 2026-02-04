import json
import logging
from django.http import JsonResponse, HttpRequest
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required

from authentication.guards import session_login_required, role_required
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.repositories.queries.maternal_health_record_queries import MaternalHealthRecordQueries
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException

logger = logging.getLogger(__name__)

MIDWIFE_ROLES = ("MIDWIFE", "Midwife", "midwife")


@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*MIDWIFE_ROLES), name="dispatch")
@method_decorator(csrf_required, name="dispatch")
class PostpartumFollowupMidwifeAPI(View):
    """API endpoint for Midwife to update postpartum visit findings/notes for today's visit.

    Expects JSON with `maternal_record_id` and at least one of:
      - findings (text)
      - notes (text)

    Returns JSON { success: bool } on success.
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
        findings = payload.get('findings')
        notes = payload.get('notes')

        if not findings and not notes:
            return JsonResponse({'success': False, 'message': 'Either findings or notes must be provided.'}, status=400)

        conn = ConnectionAdapter()
        repo = MaternalHealthRecordRepository(conn)
        queries = MaternalHealthRecordQueries(conn)

        try:
            # Fetch the latest postpartum visit row to check if findings/notes already exist
            latest_pp_row = queries.get_postpartum_visit_rows_by_mhr_id(mhr_id)
            
            if latest_pp_row:
                # Check the most recent row (first in list since ordered DESC)
                most_recent = latest_pp_row[0]
                existing_findings = most_recent.get('findings')
                existing_notes = most_recent.get('nurse_notes')
                
                # Consider findings/notes as filled if they exist, are not empty, and are not 'N/A'
                findings_filled = existing_findings and existing_findings.strip() and existing_findings.strip().upper() != 'N/A'
                notes_filled = existing_notes and existing_notes.strip() and existing_notes.strip().upper() != 'N/A'
                
                if findings_filled or notes_filled:
                    return JsonResponse({
                        'success': False, 
                        'message': 'Findings and/or notes have already been provided for the latest postpartum visit. Cannot update again.'
                    }, status=400)

            res = repo.update_postpartum_visit_row_findings(
                p_maternal_record_id=mhr_id,
                p_performed_by_id=staff_id,
                p_findings=findings,
                p_nurse_notes=notes,
            )
            
            if not res:
                return JsonResponse({'success': False, 'message': 'Failed to update postpartum findings.'}, status=500)
            
            complete_visit = repo.complete_postpartum_visit_and_schedule(mhr_id=mhr_id, staff_id=staff_id)

            return JsonResponse({'success': True, 'message': 'Postpartum findings updated.'})

        except MaternalHealthRecordException as e:
            return JsonResponse({'success': False, 'message': e.message or str(e)}, status=400)
        except Exception:
            logger.exception('Unexpected error in PostpartumFollowupMidwifeAPI')
            return JsonResponse({'success': False, 'message': 'Unexpected server error.'}, status=500)
