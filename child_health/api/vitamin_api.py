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
from barug.utility.custom_date_time_util import DateAndTimeUtility
from barug.containers import app
from src.app.services.vitamin_service import VitaminService

logger = logging.getLogger(__name__)

ACCESS = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")


def _repo():
    return ChildHealthRecordRepository(ctx=ConnectionAdapter())


@method_decorator([session_login_required, role_required(*ACCESS), nocache, csrf_protect, require_http_methods(["POST"])], name='dispatch')
class VitaminAPI(View):
    def post(self, request: HttpRequest, child_health_record_id: int) -> JsonResponse:
        try:
            data = request.POST.dict() if request.POST else (json.loads(request.body or "{}") or {})
            staff_id = request.session.get("auth").get("staff_id")
            # Accept either a pre-computed stage id or checkbox flags
            stage_id = data.get("vit_a_stage")
            requested_stages = []
            for s in (1, 2, 3):
                key = f"vit_a_{s}"
                val = data.get(key)
                # HTML checkboxes may send 'on' or 'true' or boolean-like values; treat presence as selection
                if val in (True, "True", "true", "on", "1", 1) or str(val).lower() in ("true", "on", "1"):
                    requested_stages.append(s)

            # Resolve service via DI container
            vitamin_service: VitaminService = app.vitamin_service()

            print(f"Applying Vitamin A stage {stage_id} for CHR ID {child_health_record_id} by staff {staff_id}")
            # Let the service orchestrate validation and persistence. It will
            # raise ChildHealthRecordException on validation errors.
            response = vitamin_service.apply_stage(
                child_health_record_id=child_health_record_id,
                staff_id=staff_id,
                stage_id=(int(stage_id) if stage_id else None),
                requested_stages=requested_stages or None,
            )
            if response:
                return JsonResponse({"ok": True, "message": "Vitamin A data saved"})
            return JsonResponse({"ok": False, "message": "Failed to save Vitamin A data"}, status=500)
        except ChildHealthRecordException as chre:
            logger.warning("ChildHealthRecordException in VitaminAPI: %s", getattr(chre, 'message', str(chre)))
            return JsonResponse({"ok": False, "error": getattr(chre, 'message', str(chre))}, status=400)
        except Exception as e:
            logger.exception("VitaminAPI failed: %s", e)
            return JsonResponse({"ok": False, "error": "Internal Server Error"}, status=500)
