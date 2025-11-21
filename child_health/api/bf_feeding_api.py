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
from dependency_injector.wiring import inject, Provide
from src.app.bootstrap.app_containers import AppContainer
from src.app.contracts.bf_feeding_service import IBFFeedingService
from src.domain.exceptions.bf_feeding_domain_exception import BfFeedingDomainException

logger = logging.getLogger(__name__)

ACCESS = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")



@method_decorator([session_login_required, role_required(*ACCESS), nocache, csrf_protect, require_http_methods(["POST"])], name='dispatch')
class BFFeedingAPI(View):
    @inject
    def __init__(self, bf_service: IBFFeedingService = Provide[AppContainer.child_bf_service], **kwargs):
        super().__init__(**kwargs)
        self.bf_service = bf_service

    def post(self, request: HttpRequest, child_health_record_id: int) -> JsonResponse:
        try:
            data = request.POST.dict() if request.POST else (json.loads(request.body or "{}") or {})
            staff_id = request.session.get("auth").get("staff_id")

            # Delegate validation and insertion to service layer (injected)
            bf_service: IBFFeedingService = self.bf_service
            res = bf_service.process_and_insert(chr_id=child_health_record_id, staff_id=staff_id, payload=data)
            if res:
                return JsonResponse({"ok": True, "message": "Breast feeding saved"})
            return JsonResponse({"ok": False, "message": "Failed to save BF data"}, status=500)
        except ChildHealthRecordException as chre:
            logger.warning("ChildHealthRecordException in BFFeedingAPI: %s", getattr(chre, 'message', str(chre)))
            return JsonResponse({"ok": False, "error": getattr(chre, 'message', str(chre))}, status=400)
        except Exception as e:
            logger.exception("BFFeedingAPI failed: %s", e)
            return JsonResponse({"ok": False, "error": "Internal Server Error"}, status=500)
