import json
import os
from django.http import HttpResponse, JsonResponse, HttpRequest, StreamingHttpResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required

from authentication.guards import session_login_required, role_required
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.app.services.image_download_service import ImageDownloadService
from dependency_injector.wiring import inject, Provide
from barug.containers import app


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

    @inject
    def post(self, request: HttpRequest, svc: ImageDownloadService = Provide[app.image_download_service], *args, **kwargs):
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
            mhr_id = payload.get('mhr_id')
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid JSON payload.'}, status=400)
        return self._handle_request(request, mhr_id, svc)

    def _handle_request(self, request: HttpRequest, mhr_id, svc: ImageDownloadService = None):
        if not mhr_id:
            return JsonResponse({'success': False, 'message': 'Missing mhr_id parameter.'}, status=400)
        try:
            mhr_id = int(mhr_id)
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid mhr_id parameter.'}, status=400)

        # service is injected for DI; if not provided or not resolved, fall back to resolving
        # from the application container or constructing a local instance.
        try:
            need_resolve = not svc or not hasattr(svc, 'zip_lab_images_for_maternal_record')
        except Exception:
            need_resolve = True

        if need_resolve:
            # Prefer resolving from the wired container (if available)
            try:
                svc = app.image_download_service()
            except Exception:
                # Last-resort: construct using fresh repo+service
                repo = MaternalHealthRecordRepository(ConnectionAdapter())
                svc = ImageDownloadService(repo)

        try:
            tmp_path, zip_name = svc.zip_lab_images_for_maternal_record(mhr_id)
        except ValueError as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=404)
        except Exception as e:
            import logging
            logging.exception('Failed to build zip for mhr %s', mhr_id)
            return JsonResponse({'success': False, 'message': 'Server error building ZIP.'}, status=500)

        # Stream the temporary zip file back to the client and remove it after
        def file_iterator(path, chunk_size=8192):
            try:
                with open(path, 'rb') as fh:
                    while True:
                        chunk = fh.read(chunk_size)
                        if not chunk:
                            break
                        yield chunk
            finally:
                try:
                    os.remove(path)
                except Exception:
                    pass

        size = None
        try:
            size = os.path.getsize(tmp_path)
        except Exception:
            size = None

        resp = StreamingHttpResponse(file_iterator(tmp_path), content_type='application/zip')
        resp['Content-Disposition'] = f'attachment; filename="{zip_name}"'
        if size:
            resp['Content-Length'] = str(size)
        return resp
