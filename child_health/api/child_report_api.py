import os
import json
import logging

from django.http import HttpResponse, HttpRequest, JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required

from authentication.guards import session_login_required, role_required
from dependency_injector.wiring import inject, Provide
from barug import containers as app

from barug.settings import BASE_DIR
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.exceptions.child_health_record_exceptions import ChildHealthRecordException
from src.infra.repositories.child_report_repository import ChildReportRepository
from src.app.services.child_report_service import ChildReportService
from src.infra.utilities.pdf_generator import PdfGenerator

logger = logging.getLogger(__name__)

ALLOWED_ROLES = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")


@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*ALLOWED_ROLES), name="dispatch")
@method_decorator(csrf_required, name="dispatch")
class ChildReportAPI(View):
    """Return a generated Child Health Summary PDF for a child health record.

    Query params:
      - child_record_id: integer (required)
    """

    def get(self, request: HttpRequest, *args, **kwargs):
        # resolve repository provider (try DI container first, fall back to direct construction)
        try:
            if hasattr(app, 'infra') and hasattr(app.infra, 'child_report_repository'):
                try:
                    repo = app.infra.child_report_repository()
                except Exception:
                    repo = ChildReportRepository(ConnectionAdapter())
            else:
                repo = ChildReportRepository(ConnectionAdapter())
        except Exception:
            logger.exception('Error resolving child_report_repository provider')
            return JsonResponse({'success': False, 'message': 'Unexpected server error.'}, status=500)

        child_id = request.GET.get('child_record_id')
        if not child_id:
            return JsonResponse({'success': False, 'message': 'child_record_id is required.'}, status=400)
        try:
            child_id = int(child_id)
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'message': 'child_record_id must be an integer.'}, status=400)

        # optional overrides
        header_lines_param = request.GET.get('header_lines')
        watermark_param = request.GET.get('watermark')
        left_image_param = request.GET.get('left_image')
        right_image_param = request.GET.get('right_image')

        header_lines = None
        if header_lines_param:
            try:
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
                header_lines = None

        # set default banner/logo if none provided
        if not left_image_param and not right_image_param:
            try:
                default_logo_path = os.path.join(BASE_DIR, 'static', 'images', 'brgy-sto-nino.png')
                if os.path.exists(default_logo_path):
                    left_image_param = default_logo_path
            except Exception:
                logger.exception('Error resolving default logo path')
                left_image_param = None

        try:
            service = ChildReportService(repo, pdf_generator=PdfGenerator())

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

            pdf_bytes = service.generate_child_summary_pdf(
                child_id,
                header_lines=header_lines,
                watermark=watermark_param,
                left_image=left_image_param,
                right_image=right_image_param,
                generated_by_name=gen_name,
                generated_by_role=gen_role,
            )

            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            filename = f"child_summary_{child_id}.pdf"
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            return response
        except ChildHealthRecordException as chre:
            return JsonResponse({'success': False, 'message': str(chre)}, status=404)
        except Exception:
            logger.exception('Failed generating child report for child_record %s', child_id)
            return JsonResponse({'success': False, 'message': 'Failed to generate report.'}, status=500)
