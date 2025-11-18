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
class NewbornScreeningAPI(View):
    def post(self, request: HttpRequest, child_health_record_id: int) -> JsonResponse:
        try:
            data = request.POST.dict() if request.POST else (json.loads(request.body or "{}") or {})
            staff_id = request.session.get("auth").get("staff_id")
            feeding_type = data.get("type_of_feeding")
            referred_for_newborn_screening = data.get("referred_for_newborn_screening")

            repo = _repo()
            is_success = repo.insert_new_born_screening_date(
                p_child_record_id=child_health_record_id,
                p_assessed_by_id=staff_id,
                feeding_type_id=feeding_type,
                p_referred_nbs_date=referred_for_newborn_screening,
            )
            if is_success:
                return JsonResponse({"ok": True, "message": "Newborn Screening saved"})
            return JsonResponse({"ok": False, "message": "Failed to save Newborn Screening"}, status=500)
        except ChildHealthRecordException as chre:
            logger.warning("ChildHealthRecordException in NewbornScreeningAPI: %s", getattr(chre, 'message', str(chre)))
            return JsonResponse({"ok": False, "error": getattr(chre, 'message', str(chre))}, status=400)
        except Exception as e:
            logger.exception("NewbornScreeningAPI failed: %s", e)
            return JsonResponse({"ok": False, "error": "Internal Server Error"}, status=500)
