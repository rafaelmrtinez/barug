from django.views import View
from django.http import JsonResponse
from django.utils.decorators import method_decorator
import json

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from barug.utility.lazy_repository import LazyRepositoryProxy
from src.infra.database.connection_adapter import ConnectionAdapter
import logging
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from dependency_injector.wiring import inject, Provide
from src.app.bootstrap.app_containers import AppContainer
from src.app.services.obstetric_validation_service import (
    ObstetricValidationException,
    ServiceExecutionException,
    ObstetricValidationService,
)
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException


ACCESS = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")

REPOSITORY: MaternalHealthRecordRepository = LazyRepositoryProxy(repo_factory=lambda: MaternalHealthRecordRepository(ConnectionAdapter()))

LOG = logging.getLogger(__name__)


@method_decorator(session_login_required, name='dispatch')
@method_decorator(role_required(*ACCESS), name='dispatch')
@method_decorator(nocache, name='dispatch')
class ObstetricHistoryAPI(View):
    """Accept POST to save obstetric history.

    Uses the existing `ObstetricHistoryForm` as a lightweight serializer to
    parse incoming data. Full cross-field/business validations have been
    moved into the service layer; those service errors are mapped into a
    JSON response so the frontend can display them.
    """

    @inject
    def post(self, request, *args, service: ObstetricValidationService = Provide[AppContainer.obstetric_validation_service], **kwargs):
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

        # Validate payload via the injected service (chronological checks).
        try:
            res = service.save_obstetric_history(payload, staff_id)
        except ObstetricValidationException as e:
            # Shouldn't normally happen because we validate above, but
            # handle defensively.
            response = {'success': False, 'message': str(e)}
            if getattr(e, 'errors', None):
                response['errors'] = e.errors
            return JsonResponse(response, status=400)
        except MaternalHealthRecordException as e:
            # Domain-level validation or constraint from DB layer; surface
            # a friendly message to the client without leaking internals.
            msg = getattr(e, 'message', str(e))
            return JsonResponse({'success': False, 'message': msg}, status=400)
        except ServiceExecutionException:
            LOG.exception('Failed to save obstetric history for mhr_id=%s', mhr_id)
            return JsonResponse({'success': False, 'message': 'Failed to save.'}, status=500)
        except Exception:
            LOG.exception('Unexpected error while saving obstetric history for mhr_id=%s', mhr_id)
            return JsonResponse({'success': False, 'message': 'Failed to save.'}, status=500)

        if not res:
            return JsonResponse({'success': False, 'message': 'Failed to save.'}, status=500)

        return JsonResponse({'success': True, 'message': 'Obstetric History saved.'})
