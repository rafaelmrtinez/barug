from django.views import View
from django.http import JsonResponse
from django.utils.decorators import method_decorator
import json

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from dependency_injector.wiring import inject, Provide
from src.app.bootstrap.app_containers import AppContainer
from src.app.services.prenatal_followup_service import (
    PrenatalFollowUpValidationException,
    ServiceExecutionException,
    PrenatalFollowUpService,
)
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException
from barug.utility.lazy_repository import LazyRepositoryProxy
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository

ACCESS = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")

REPOSITORY: MaternalHealthRecordRepository = LazyRepositoryProxy(repo_factory=lambda: MaternalHealthRecordRepository(ConnectionAdapter()))


@method_decorator(session_login_required, name='dispatch')
@method_decorator(role_required(*ACCESS), name='dispatch')
@method_decorator(nocache, name='dispatch')
class PrenatalFollowUpEntryAPI(View):
    """Accept POST to save a prenatal follow-up entry via PrenatalFollowUpService."""

    @inject
    def post(self, request, *args, service: PrenatalFollowUpService = Provide[AppContainer.prenatal_followup_service], **kwargs):
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
        staff_role = request.session.get('auth', {}).get('role_name')

        # Detect prefix usage (frontend may prefix fields with pf_entry-)
        uses_prefix = any(str(k).startswith('pf_entry-') for k in payload.keys())

        try:
            res = service.save_followup(payload, staff_id=staff_id, role=staff_role, prefix='pf_entry' if uses_prefix else None)
        except PrenatalFollowUpValidationException as e:
            response = {'success': False, 'message': str(e)}
            if getattr(e, 'errors', None):
                try:
                    first_field = next(iter(e.errors))
                    msgs = e.errors.get(first_field)
                    first_msg = msgs[0] if isinstance(msgs, (list, tuple)) and msgs else str(e)
                    response['errors'] = {first_field: [first_msg]}
                except Exception:
                    response['errors'] = {'error': [str(e)]}
            return JsonResponse(response, status=400)
        except MaternalHealthRecordException as e:
            msg = getattr(e, 'message', str(e))
            return JsonResponse({'success': False, 'message': msg}, status=400)
        except NotImplementedError:
            return JsonResponse({'success': False, 'message': 'Midwife update not implemented.'}, status=501)
        except ServiceExecutionException:
            return JsonResponse({'success': False, 'message': 'Failed to save.'}, status=500)
        except Exception:
            return JsonResponse({'success': False, 'message': 'Failed to save.'}, status=500)

        if not res:
            return JsonResponse({'success': False, 'message': 'Failed to save.'}, status=500)

        return JsonResponse({'success': True, 'message': 'Prenatal Follow-up saved.'})
