from django.views import View
from django.http import JsonResponse
from django.utils.decorators import method_decorator
import json

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from barug.utility.lazy_repository import LazyRepositoryProxy
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from dependency_injector.wiring import inject, Provide
from src.app.bootstrap.app_containers import AppContainer
from src.app.services.tetanus_toxoid_service import (
    TetanusToxoidService,
    TetanusToxoidValidationException,
    ServiceExecutionException,
)
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException

ACCESS = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")

REPOSITORY: MaternalHealthRecordRepository = LazyRepositoryProxy(repo_factory=lambda: MaternalHealthRecordRepository(ConnectionAdapter()))


@method_decorator(session_login_required, name='dispatch')
@method_decorator(role_required(*ACCESS), name='dispatch')
@method_decorator(nocache, name='dispatch')
class TetanusToxoidAPI(View):
    """Accept POST to save tetanus toxoid record."""

    @inject
    def post(self, request, *args, service: TetanusToxoidService = Provide[AppContainer.tetanus_toxoid_service], **kwargs):
        try:
            if request.content_type and request.content_type.startswith('application/json'):
                payload = json.loads(request.body.decode('utf-8') or '{}')
            else:
                payload = {k: v for k, v in request.POST.items()}
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid payload.'}, status=400)

        mhr_id = payload.get('mhr_id') or kwargs.get('mhr_id')
        if not mhr_id:
            return JsonResponse({'success': False, 'message': 'Missing mhr_id.'}, status=400)

        staff_id = request.session.get('auth', {}).get('staff_id')

        try:
            res = service.save_tetanus_tt(payload, staff_id)
        except TetanusToxoidValidationException as e:
            response = {'success': False, 'message': str(e)}
            if getattr(e, 'errors', None):
                response['errors'] = e.errors
            return JsonResponse(response, status=400)
        except MaternalHealthRecordException as e:
            msg = getattr(e, 'message', str(e))
            return JsonResponse({'success': False, 'message': msg}, status=400)
        except ServiceExecutionException:
            return JsonResponse({'success': False, 'message': 'Failed to save.'}, status=500)
        except Exception:
            return JsonResponse({'success': False, 'message': 'Failed to save.'}, status=500)

        if not res:
            return JsonResponse({'success': False, 'message': 'Failed to save.'}, status=500)

        return JsonResponse({'success': True, 'message': 'Tetanus Toxoid saved.'})
