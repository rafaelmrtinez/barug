import json
from django.http import HttpResponse, JsonResponse, HttpRequest
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required

from authentication.guards import session_login_required, role_required
from src.infra.database.connection_adapter import ConnectionAdapter
from maternal.repository import MaternalHealthRecordRepository
from src.app.services.image_download_service import ImageDownloadService


ALLOWED_ROLES = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")


@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*ALLOWED_ROLES), name="dispatch")
@method_decorator(csrf_required, name="dispatch")
class DownloadImageDownload(View):
    """API endpoint that returns a ZIP containing all laboratory images for a maternal record.

    Accepts GET with query param `mhr_id` or POST with JSON body { "mhr_id": <id> }.
    Returns a binary application/zip response on success.
    """

    def get(self, request: HttpRequest, *args, **kwargs):
        mhr_id = request.GET.get('mhr_id')
        return self._handle_request(request, mhr_id)

    def post(self, request: HttpRequest, *args, **kwargs):
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
            mhr_id = payload.get('mhr_id')
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid JSON payload.'}, status=400)
        return self._handle_request(request, mhr_id)

    def _handle_request(self, request: HttpRequest, mhr_id):
        if not mhr_id:
            return JsonResponse({'success': False, 'message': 'Missing mhr_id parameter.'}, status=400)
        try:
            mhr_id = int(mhr_id)
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid mhr_id parameter.'}, status=400)

        repo = MaternalHealthRecordRepository(ConnectionAdapter())
        svc = ImageDownloadService(repo)

        try:
            zip_bytes, zip_name = svc.zip_lab_images_for_maternal_record(mhr_id)
        except ValueError as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=404)
        except Exception as e:
            import logging
            logging.exception('Failed to build zip for mhr %s', mhr_id)
            return JsonResponse({'success': False, 'message': 'Server error building ZIP.'}, status=500)

        response = HttpResponse(zip_bytes, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{zip_name}"'
        return response
