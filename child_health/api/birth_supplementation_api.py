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
from src.app.contracts.birth_supplementation_service import IBirthSupplementationService
from src.domain.exceptions.birth_supplementation_domain_exception import BirthSupplementationDomainException

logger = logging.getLogger(__name__)

ACCESS = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")


@method_decorator([session_login_required, role_required(*ACCESS), nocache, csrf_protect, require_http_methods(["POST"])], name='dispatch')
class BirthSupplementationAPI(View):
    @inject
    def __init__(self, birth_service: IBirthSupplementationService = Provide[AppContainer.birth_supplementation_service], **kwargs):
        super().__init__(**kwargs)
        self.birth_service = birth_service
    def post(self, request: HttpRequest, child_health_record_id: int) -> JsonResponse:
        try:
            data = request.POST.dict() if request.POST else (json.loads(request.body or "{}") or {})
            staff_id = request.session.get("auth").get("staff_id")

            # Map fields directly from POST (no form validation)
            date_assessed = data.get("data_assessed")
            anemic_seen = data.get("anemia_2_59_seen")
            anemic_given_iron = data.get("anemia_2_59_given_iron")
            birth_weight = data.get("birth_weight")
            is_low_birth_weight = data.get("low_birth_weight")
            seen_2_6_mos = data.get("birth_wt_seen")
            given_2_6_mos = data.get("birth_wt_given_iron")
            tt_status = data.get("tt_id")

            result = self.birth_service.insert_birth_supplementation(
                child_record_id=child_health_record_id,
                assessed_by_id=staff_id,
                date_assessed=date_assessed or None,
                anemic_seen=anemic_seen or None,
                anemic_given_iron=anemic_given_iron or None,
                birth_weight=birth_weight or None,
                is_low_birth_weight=is_low_birth_weight or None,
                seen_2_6_mos=seen_2_6_mos or None,
                given_2_6_mos=given_2_6_mos or None,
                tt_status=tt_status or None,
            )
            if not result:
                return JsonResponse({"ok": False, "message": "Failed to save Birth and Supplementation"}, status=500)
            return JsonResponse({"ok": True, "message": "Birth and Supplementation saved"})
        except BirthSupplementationDomainException as bd:
            logger.warning("Domain validation error in BirthSupplementationAPI: %s", getattr(bd, 'message', str(bd)))
            return JsonResponse({"ok": False, "error": getattr(bd, 'message', str(bd))}, status=400)
        except ChildHealthRecordException as chre:
            logger.warning("ChildHealthRecordException in BirthSupplementationAPI: %s", getattr(chre, 'message', str(chre)))
            return JsonResponse({"ok": False, "error": getattr(chre, 'message', str(chre))}, status=400)
        except Exception as e:
            logger.exception("BirthSupplementationAPI failed: %s", e)
            return JsonResponse({"ok": False, "error": "Internal Server Error"}, status=500)
