from django.views import View
from django.http import JsonResponse
from django.utils.decorators import method_decorator
import json

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from dependency_injector.wiring import inject, Provide
from src.app.bootstrap.app_containers import AppContainer
from src.app.services.create_maternal_health_record_service import CreateMaternalHealthRecordService
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException

ACCESS = ("Barangay Health Worker", "bhw", "MIDWIFE", "Midwife", "midwife", "Super Admin")


@method_decorator(session_login_required, name='dispatch')
@method_decorator(role_required(*ACCESS), name='dispatch')
@method_decorator(nocache, name='dispatch')
class CreateMaternalHealthRecordAPI(View):
    """API endpoint to create a maternal health record.

    Expects JSON body with the following keys (JSON):
      - person_id (int)
      - weight (decimal/float)
      - height (decimal/float)
      - bmi_status_id (int)
      - is_transferred or is_transfered (bool, optional)
      - husband_id (optional int)

    Delegates to CreateMaternalHealthRecordService which calls the repository.
    """

    @inject
    def post(self, request, *args, service: CreateMaternalHealthRecordService = Provide[AppContainer.create_maternal_health_record_service], **kwargs):
        try:
            if request.content_type and request.content_type.startswith('application/json'):
                payload = json.loads(request.body.decode('utf-8') or '{}')
            else:
                payload = {k: v for k, v in request.POST.items()}
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid payload.'}, status=400)

        # required fields
        person_id = payload.get('person_id')
        weight = payload.get('weight')
        height = payload.get('height')
        bmi_status_id = payload.get('bmi_status_id')

        if not person_id:
            return JsonResponse({'success': False, 'message': 'Missing person_id.'}, status=400)

        staff_id = request.session.get('auth', {}).get('staff_id')

        # accept either spelling for transferred flag
        is_transferred = payload.get('is_transferred') if 'is_transferred' in payload else payload.get('is_transfered', False)
        husband_id = payload.get('husband_id')

        try:
            res = service.create_maternal_health_record(
                staff_id=staff_id,
                person_id=int(person_id),
                husband_id=(int(husband_id) if husband_id is not None and husband_id != '' else None),
                weight=(float(weight) if weight is not None and weight != '' else None),
                height=(float(height) if height is not None and height != '' else None),
                bmi_status_id=(int(bmi_status_id) if bmi_status_id is not None and bmi_status_id != '' else None),
                is_transferred=bool(is_transferred),
            )
        except MaternalHealthRecordException as e:
            msg = getattr(e, 'message', str(e))
            return JsonResponse({'success': False, 'message': msg}, status=400)
        except Exception:
            return JsonResponse({'success': False, 'message': 'Failed to create maternal health record.'}, status=500)

        if not res:
            return JsonResponse({'success': False, 'message': 'Failed to create maternal health record.'}, status=500)

        return JsonResponse({'success': True, 'message': 'Maternal health record created.', 'data': res})
