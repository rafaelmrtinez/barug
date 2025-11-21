import logging
import json
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from django.views import View
from django.utils.decorators import method_decorator

from authentication.guards import role_required, session_login_required
from authentication.utils import nocache
from src.infra.exceptions.child_health_record_exception import ChildHealthRecordException
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.child_health_record_repository import ChildHealthRecordRepository
from src.app.transfer_objects.request.child_health_version_two.child_monitoring_log import ChildMonitoringLog
from barug.containers import app
from src.app.services.child_visit_service import ChildVisitService

logger = logging.getLogger(__name__)

ACCESS = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")


def _repo():
    return ChildHealthRecordRepository(ctx=ConnectionAdapter())


@method_decorator([session_login_required, role_required(*ACCESS), nocache, csrf_protect, require_http_methods(["POST"])], name='dispatch')
class ChildVisitAPI(View):
    def post(self, request: HttpRequest, child_health_record_id: int) -> JsonResponse:
        try:
            data = request.POST.dict() if request.POST else (json.loads(request.body or "{}") or {})
            staff_id = request.session.get("auth").get("staff_id")
            # Delegate validation/normalization and persistence to service layer
            child_visit_service: ChildVisitService = app.child_visit_service()
            res = child_visit_service.process_and_insert(chr_id=child_health_record_id, staff_id=staff_id, payload=data)
            return JsonResponse({"ok": True, "message": "Child monitoring log saved"})
        except ChildHealthRecordException as chre:
            logger.warning("ChildHealthRecordException in ChildVisitAPI: %s", getattr(chre, 'message', str(chre)))
            return JsonResponse({"ok": False, "error": getattr(chre, 'message', str(chre))}, status=400)
        except Exception as e:
            logger.exception("ChildVisitAPI failed: %s", e)
            return JsonResponse({"ok": False, "error": "Internal Server Error"}, status=500)
