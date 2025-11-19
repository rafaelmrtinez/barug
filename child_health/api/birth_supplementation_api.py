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

logger = logging.getLogger(__name__)

ACCESS = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")


def _repo():
    return ChildHealthRecordRepository(ctx=ConnectionAdapter())


@method_decorator([session_login_required, role_required(*ACCESS), nocache, csrf_protect, require_http_methods(["POST"])], name='dispatch')
class BirthSupplementationAPI(View):
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

            repo = _repo()
            result = repo.insert_child_screening(
                chr_id=child_health_record_id,
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
        except ChildHealthRecordException as chre:
            logger.warning("ChildHealthRecordException in BirthSupplementationAPI: %s", getattr(chre, 'message', str(chre)))
            return JsonResponse({"ok": False, "error": getattr(chre, 'message', str(chre))}, status=400)
        except Exception as e:
            logger.exception("BirthSupplementationAPI failed: %s", e)
            return JsonResponse({"ok": False, "error": "Internal Server Error"}, status=500)
