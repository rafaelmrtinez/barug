import json
from datetime import date, time

from django.http import JsonResponse, HttpRequest, HttpResponseRedirect
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required

from authentication.guards import session_login_required, role_required
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException
from src.app.services.maternal_postpartum_service import MaternalPostpartumService


ALLOWED_ROLES = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")


@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*ALLOWED_ROLES), name="dispatch")
@method_decorator(csrf_required, name="dispatch")
class PostpartumRecordAPI(View):
    """API to insert a postpartum record.

    Accepts form-encoded POST (from modal) or JSON body. If called via form POST,
    redirects back to the record_detail page on success. If called with JSON, returns JSON.
    """

    def post(self, request: HttpRequest, *args, **kwargs):
        # Accept both JSON and form-encoded
        payload = None
        if request.content_type and 'application/json' in request.content_type:
            try:
                payload = json.loads(request.body.decode('utf-8') or '{}')
            except Exception:
                return JsonResponse({'success': False, 'message': 'Invalid JSON payload.'}, status=400)
        else:
            # use POST dict
            payload = {k: v for k, v in request.POST.items()}

        # The service layer handles validation and sanitation. Build repo+service and delegate.
        staff_id = request.session.get('auth', {}).get('staff_id')
        staff_role = request.session.get('auth', {}).get('role_name')
        try:
            staff_id = int(staff_id)
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid staff id in session.'}, status=400)

        repo = MaternalHealthRecordRepository(ConnectionAdapter())
        service = MaternalPostpartumService(repo)

        try:
            # service will validate/sanitize payload and perform insert
            res = service.insert_postpartum_record(payload or {}, added_by_id=staff_id, attended_by_role_name=staff_role)
        except MaternalHealthRecordException as e:
            if request.content_type and 'application/json' in (request.content_type or ''):
                return JsonResponse({'success': False, 'message': e.message or str(e)}, status=400)
            request.session['postpartum_api_error'] = e.message or str(e)
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))
        except Exception as e:
            import logging
            logging.exception('Unexpected error inserting postpartum record')
            if request.content_type and 'application/json' in (request.content_type or ''):
                return JsonResponse({'success': False, 'message': 'Unexpected server error.'}, status=500)
            request.session['postpartum_api_error'] = 'Unexpected server error.'
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

        if not res:
            if request.content_type and 'application/json' in (request.content_type or ''):
                return JsonResponse({'success': False, 'message': 'Failed to save postpartum record.'}, status=500)
            request.session['postpartum_api_error'] = 'Failed to save postpartum record.'
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

        if request.content_type and 'application/json' in (request.content_type or ''):
            return JsonResponse({'success': True, 'message': 'Postpartum record saved.', 'result': res})

        # form POST -> redirect back to referring page
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))
