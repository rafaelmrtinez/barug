import json
from django.http import JsonResponse, HttpRequest
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required

from authentication.guards import session_login_required, role_required
import datetime
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository


ALLOWED_ROLES = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")


@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*ALLOWED_ROLES), name="dispatch")
@method_decorator(csrf_required, name="dispatch")
class MhrSidePanelAPI(View):
    """Return JSON data used to populate the maternal side panel for a given maternal record id.

    Query params:
      - mhr_id: integer (required)
    """

    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        mhr_id = request.GET.get('mhr_id')
        if not mhr_id:
            return JsonResponse({'success': False, 'message': 'mhr_id is required.'}, status=400)
        try:
            mhr_id = int(mhr_id)
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'message': 'mhr_id must be an integer.'}, status=400)

        repo = MaternalHealthRecordRepository(ConnectionAdapter())

        try:
            # Delegate to the repository helper which returns the ANC trimester tracker
            # (may be a single dict or a list of dicts).
            tracker = repo.fetch_anc_trimester_tracker_by_mhr_id(mhr_id)

            # Include latest scheduled visit info (union of prenatal/postpartum)
            latest_visit = None
            try:
                latest_visit = repo.fetch_latest_scheduled_visit_by_mhr_id(mhr_id)
            except Exception:
                # non-fatal for side-panel - log and continue
                import logging
                logging.exception('Error fetching latest scheduled visit for mhr %s', mhr_id)

            # Also fetch latest prenatal and postpartum schedules separately so the UI
            # Fetch full prenatal and postpartum schedule histories (for history modals)
            prenatal_history = []
            postpartum_history = []
            try:
                prenatal_history = repo.fetch_all_prenatal_scheduled_by_mhr_id(mhr_id) or []
            except Exception:
                import logging
                logging.exception('Error fetching prenatal schedule history for mhr %s', mhr_id)

            try:
                postpartum_history = repo.fetch_all_postpartum_scheduled_by_mhr_id(mhr_id) or []
            except Exception:
                import logging
                logging.exception('Error fetching postpartum schedule history for mhr %s', mhr_id)

        except Exception:
            import logging
            logging.exception('Error fetching side panel data for mhr %s', mhr_id)
            return JsonResponse({'success': False, 'message': 'Unexpected server error.'}, status=500)

        # Format latest_visit date/time into serializable strings to avoid
        # frontend slicing and timezone issues.
        if latest_visit:
            try:
                sd = latest_visit.get('scheduled_date')
                st = latest_visit.get('scheduled_time')
                ca = latest_visit.get('created_at')
                if sd:
                    # date -> YYYY-MM-DD
                    latest_visit['scheduled_date_str'] = sd.isoformat()
                if st:
                    # time -> HH:MM
                    try:
                        latest_visit['scheduled_time_hm'] = st.strftime('%H:%M')
                    except Exception:
                        latest_visit['scheduled_time_hm'] = str(st)
                if ca:
                    try:
                        latest_visit['created_at_iso'] = ca.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                    except Exception:
                        latest_visit['created_at_iso'] = str(ca)
            except Exception:
                import logging
                logging.exception('Error formatting latest_scheduled_visit for mhr %s', mhr_id)

        payload = {
            'result': tracker or {},
            'latest_scheduled_visit': latest_visit or {},
            'prenatal_schedule_history': prenatal_history,
            'postpartum_schedule_history': postpartum_history,
        }

        return JsonResponse({'success': True, **payload})
