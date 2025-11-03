import base64
import json
import logging

from django.http import JsonResponse, HttpRequest
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required

from dependency_injector.wiring import inject, Provide
from barug.containers import app

from authentication.guards import session_login_required, role_required
from src.app.services.faq_ingestion_service import FAQIngestionService, FAQValidationError

logger = logging.getLogger(__name__)


# restrict to admin-like roles for FAQ management
ALLOWED_ROLES = ("admin", "Admin", "Super Admin", "super admin")


@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*ALLOWED_ROLES), name="dispatch")
@method_decorator(csrf_required, name="dispatch")
class FAQIngestAPI(View):
    """Accept FAQ uploads either as JSON (base64 fileData) or multipart/form-data.

    Uses dependency injection to obtain the ingestion service.
    """

    @inject
    def post(self, request: HttpRequest, service: FAQIngestionService = Provide[app.faq_ingestion_service], *args, **kwargs):
        # Accepts application/json or multipart/form-data
        content_type = request.content_type or ''

        try:
            if content_type.startswith('application/json'):
                body = request.body.decode('utf-8') if hasattr(request, 'body') else None
                if not body:
                    return JsonResponse({'success': False, 'message': 'Empty request body.'}, status=400)
                try:
                    payload = json.loads(body)
                except Exception:
                    return JsonResponse({'success': False, 'message': 'Invalid JSON.'}, status=400)

                filename = payload.get('fileName')
                filedata_b64 = payload.get('fileData')
                uploaded_by = payload.get('uploaded_by') or (request.session.get('auth', {}).get('email') if hasattr(request, 'session') else None)

                # guards
                if not filename or not filedata_b64 or not uploaded_by:
                    return JsonResponse({'success': False, 'message': 'fileName, fileData and uploaded_by are required.'}, status=400)

                try:
                    file_bytes = base64.b64decode(filedata_b64)
                except Exception:
                    return JsonResponse({'success': False, 'message': 'fileData is not valid base64.'}, status=400)

            elif content_type.startswith('multipart/form-data') or content_type.startswith('application/x-www-form-urlencoded'):
                # Expect a file field named 'file' and optional 'uploaded_by'
                upload = request.FILES.get('file')
                uploaded_by = request.POST.get('uploaded_by') or (request.session.get('auth', {}).get('first_name') + ' ' + request.session.get('auth', {}).get('last_name') if hasattr(request, 'session') else None)
                if not upload:
                    return JsonResponse({'success': False, 'message': 'No file uploaded.'}, status=400)
                filename = upload.name
                file_bytes = upload.read()
                if not uploaded_by:
                    return JsonResponse({'success': False, 'message': 'uploaded_by is required.'}, status=400)
            else:
                return JsonResponse({'success': False, 'message': 'Unsupported content type.'}, status=415)

            # Resolve injected service if needed (Provide object may be passed
            # when wiring isn't applied). Follow the project's pattern: try
            # container provider, then fall back to direct construction.
            try:
                need_resolve = not service or not hasattr(service, 'ingest_and_upload')
            except Exception:
                need_resolve = True

            if need_resolve:
                try:
                    service = app.faq_ingestion_service()
                except Exception:
                    # last-resort direct construction to avoid failing at import-time
                    from src.infra.gateways.faq_ingestion_gateway import FAQIngestionGateway
                    from src.app.services.faq_ingestion_service import FAQIngestionService

                    service = FAQIngestionService(FAQIngestionGateway())

            # Delegate to service (service performs its own guards/validation)
            result = service.ingest_and_upload(file_bytes, filename, uploaded_by)
            
            # dummy result
            # result = {
            #     'count': 0,
            #     'response': 'Dummy upload successful (no actual processing done).'
            # }
            
            return JsonResponse({'success': True, 'message': 'Uploaded', 'count': result.get('count'), 'detail': result.get('response')}, status=200)

        except FAQValidationError as ve:
            logger.warning('FAQ validation failed: %s', str(ve))
            return JsonResponse({'success': False, 'message': str(ve)}, status=400)
        except Exception as exc:
            logger.exception('Unexpected error processing FAQ upload: %s', exc)
            return JsonResponse({'success': False, 'message': 'Server error while processing upload.'}, status=500)
