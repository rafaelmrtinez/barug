import os
from django.http import HttpResponse, HttpRequest, JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required

from authentication.guards import session_login_required, role_required
from dependency_injector.wiring import inject, Provide
from barug import containers as app

from barug.settings import BASE_DIR
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException
from src.infra.repositories.maternal_report_repository import MaternalReportRepository
from src.app.services.maternal_report_service import MaternalReportService
from src.infra.utilities.pdf_generator import PdfGenerator
import json

ALLOWED_ROLES = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")


@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*ALLOWED_ROLES), name="dispatch")
@method_decorator(csrf_required, name="dispatch")
class MaternalReportAPI(View):
    """Return a generated Maternal Health Summary PDF for a maternal record.

    Query params:
      - mhr_id: integer (required)  -- maternal_record_id
    """

    @inject
    def get(self, request: HttpRequest, repo: MaternalReportRepository = Provide[app.infra.maternal_report_repository], *args, **kwargs):
        mhr_id = request.GET.get('mhr_id')
        if not mhr_id:
            return JsonResponse({'success': False, 'message': 'mhr_id is required.'}, status=400)
        try:
            mhr_id = int(mhr_id)
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'message': 'mhr_id must be an integer.'}, status=400)

        # Parse optional header overrides from query params
        header_lines_param = request.GET.get('header_lines')
        watermark_param = request.GET.get('watermark')
        left_image_param = request.GET.get('left_image')
        right_image_param = request.GET.get('right_image')
        
        # Do not set a default logo here; if the client provides a logo path
        # it will be resolved by the service, otherwise the service/view can
        # decide on any fallback behavior. The API only checks presence.

        header_lines = None
        if header_lines_param:
            try:
                # expect JSON list of {"text":..., "size":...} or list of [text,size]
                parsed = json.loads(header_lines_param)
                cleaned = []
                for item in parsed:
                    if isinstance(item, dict):
                        text = item.get('text')
                        size = item.get('size')
                        if text and size:
                            cleaned.append((text, int(size)))
                    elif isinstance(item, (list, tuple)) and len(item) >= 2:
                        cleaned.append((str(item[0]), int(item[1])))
                if cleaned:
                    header_lines = cleaned
                
            except Exception:
                # ignore parse errors and fallback to service defaults
                header_lines = None

        # Resolve repository provider; fallback to container factory or direct construction
        try:
            if not hasattr(repo, 'assemble_report_payload'):
                try:
                    # try resolving from container provider if available
                    repo = app.infra.maternal_report_repository()
                except Exception:
                    repo = MaternalReportRepository(ConnectionAdapter())
        except Exception:
            import logging
            logging.exception('Error resolving maternal_report_repository provider')
            return JsonResponse({'success': False, 'message': 'Unexpected server error.'}, status=500)

        if not left_image_param and not right_image_param:
            try:
                # if no images provided, set a default left logo
                default_logo_path = os.path.join(BASE_DIR, 'static', 'images', 'brgy-sto-nino.png')
                if os.path.exists(default_logo_path):
                    left_image_param = default_logo_path
            except Exception:
                import logging
                logging.exception('Error resolving default logo path')
                left_image_param = None

        # Construct service (inject PdfGenerator optionally)
        try:
            service = MaternalReportService(repo, pdf_generator=PdfGenerator())
            # Determine who generated the PDF from the session and pass name/role
            auth = request.session.get('auth', {}) if hasattr(request, 'session') else {}
            gen_name = None
            gen_role = None
            try:
                fn = auth.get('first_name') or ''
                ln = auth.get('last_name') or ''
                gen_name = (fn + ' ' + ln).strip() or None
                gen_role = auth.get('role_name')
            except Exception:
                gen_name = None
                gen_role = None

            result = service.generate_maternal_summary_pdf(
                mhr_id,
                header_lines=header_lines,
                watermark=watermark_param,
                left_image=left_image_param,
                right_image=right_image_param,
                generated_by_name=gen_name,
                generated_by_role=gen_role,
            )

            # Service returns (pdf_bytes, filename)
            pdf_bytes = None
            filename = None
            try:
                if isinstance(result, (tuple, list)):
                    pdf_bytes = result[0]
                    if len(result) >= 2:
                        filename = result[1]
                else:
                    pdf_bytes = result
            except Exception:
                pdf_bytes = result

            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            if not filename:
                filename = f"maternal_summary_{mhr_id}.pdf"
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            return response
        except MaternalHealthRecordException as mhe:
            return JsonResponse({'success': False, 'message': str(mhe)}, status=404)
        except Exception:
            import logging
            logging.exception('Failed generating maternal report for mhr %s', mhr_id)
            return JsonResponse({'success': False, 'message': 'Failed to generate report.'}, status=500)
