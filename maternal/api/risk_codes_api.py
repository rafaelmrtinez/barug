import json
import logging

from django.http import JsonResponse, HttpRequest, HttpResponseRedirect
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required

from authentication.guards import session_login_required, role_required
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException
from src.app.services.maternal_risk_service import MaternalRiskService
from src.infra.database.connection_adapter import ConnectionAdapter
from dependency_injector.wiring import inject, Provide
from barug.containers import app

logger = logging.getLogger(__name__)

# Allow midwife and super admin by default; adjust if needed
ALLOWED_ROLES = ("MIDWIFE", "Midwife", "midwife", "Super Admin")


@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*ALLOWED_ROLES), name="dispatch")
@method_decorator(csrf_required, name="dispatch")
class RiskCodesAPI(View):
    """API to insert/update risk codes for a maternal health record.

    Accepts JSON POST with keys:
      - maternal_record_id (int)
      - risk_categories (list[int])

    Uses `request.session.auth.staff_id` as `assessed_by`.
    """

    @inject
    def post(self, request: HttpRequest, service: MaternalRiskService = Provide[app.maternal_risk_service], *args, **kwargs):
        # parse payload
        payload = None
        if request.content_type and 'application/json' in request.content_type:
            try:
                payload = json.loads(request.body.decode('utf-8') or '{}')
            except Exception:
                return JsonResponse({'success': False, 'message': 'Invalid JSON payload.'}, status=400)
        else:
            # fallback to form data
            payload = {k: v for k, v in request.POST.items()}

        mhr_id = payload.get('maternal_record_id') or payload.get('mhr_id')
        if not mhr_id:
            return JsonResponse({'success': False, 'message': 'Missing maternal_record_id.'}, status=400)

        staff_id = request.session.get('auth', {}).get('staff_id')
        try:
            staff_id = int(staff_id)
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid staff id in session.'}, status=400)

        # risk categories may be list or comma-separated string
        categories = payload.get('risk_categories') or payload.get('categories')

        # Resolve service if DI failed
        try:
            need_resolve = not service or not hasattr(service, 'insert_risk_codes')
        except Exception:
            need_resolve = True

        if need_resolve:
            try:
                service = app.maternal_risk_service()
            except Exception:
                repo = MaternalHealthRecordRepository(ConnectionAdapter())
                service = MaternalRiskService(repo)

        try:
            res = service.insert_risk_codes(maternal_record_id=mhr_id, assessed_by_id=staff_id, risk_categories=categories)
        except MaternalHealthRecordException as e:
            return JsonResponse({'success': False, 'message': e.message or str(e)}, status=400)
        except Exception as e:
            logger.exception('Unexpected error while saving risk codes')
            return JsonResponse({'success': False, 'message': 'Unexpected server error.'}, status=500)

        if not res:
            return JsonResponse({'success': False, 'message': 'Failed to save risk codes.'}, status=500)

        return JsonResponse({'success': True, 'message': 'Risk codes saved.', 'result': res})
