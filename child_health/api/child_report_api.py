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
from src.infra.exceptions.generic_child_health_record_exceptions import GenericChildHealthRecordException
from src.infra.repositories.child_report_repository import ChildReportRepository
from src.app.services.child_report_service import ChildReportService
from src.infra.utilities.pdf_generator import PdfGenerator

logger = logging.getLogger(__name__)

ALLOWED_ROLES = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")


@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*ALLOWED_ROLES), name="dispatch")
@method_decorator(csrf_required, name="dispatch")
class ChildReportAPI(View):
    """Generate Child Health Reports based on report type.

    Query params:
      - report_type: integer (optional, default=1)
        1 = Child Summary Report (requires child_record_id)
        2 = Monthly Immunization Coverage (requires year, month)
        3 = Monthly Visit Completion (requires year, month)
        4 = Monthly Growth & Nutrition (requires year, month)
        5 = Annual Screening & Risk (requires year)
        6 = Annual Immunization Performance (requires year)
        7 = Annual Growth & Development (requires year)
        8 = All-in-One Analytics (requires year; optional month for monthly reports)
      - child_record_id: integer (required for report_type=1)
      - year: integer (required for report_type 2-8)
      - month: integer (required for report_type 2-4; optional for type 8)
    """

    def get(self, request: HttpRequest, *args, **kwargs):
        # Determine report type
        report_type = request.GET.get('report_type', '1')
        try:
            report_type = int(report_type)
            if report_type not in [1, 2, 3, 4, 5, 6, 7, 8]:
                return JsonResponse({'success': False, 'message': 'Invalid report_type. Must be 1-8.'}, status=400)
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'message': 'report_type must be an integer (1-8).'}, status=400)

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

        # Resolve reports query for analytics reports (types 2-8)
        reports_query = None
        if report_type in [2, 3, 4, 5, 6, 7, 8]:
            try:
                if hasattr(app, 'infra') and hasattr(app.infra, 'child_reports_query'):
                    try:
                        reports_query = app.infra.child_reports_query()
                    except Exception:
                        from src.infra.repositories.queries.child_reports_query import ChildReportsQuery
                        reports_query = ChildReportsQuery(ConnectionAdapter())
                else:
                    from src.infra.repositories.queries.child_reports_query import ChildReportsQuery
                    reports_query = ChildReportsQuery(ConnectionAdapter())
            except Exception:
                logger.exception('Error resolving child_reports_query provider')
                return JsonResponse({'success': False, 'message': 'Unexpected server error.'}, status=500)

        # Validate required parameters based on report type
        if report_type == 1:
            child_id = request.GET.get('child_record_id')
            if not child_id:
                return JsonResponse({'success': False, 'message': 'child_record_id is required for report_type=1.'}, status=400)
            try:
                child_id = int(child_id)
            except (TypeError, ValueError):
                return JsonResponse({'success': False, 'message': 'child_record_id must be an integer.'}, status=400)
        
        if report_type in [2, 3, 4, 5, 6, 7, 8]:
            year = request.GET.get('year')
            if not year:
                return JsonResponse({'success': False, 'message': 'year is required for analytics reports.'}, status=400)
            try:
                year = int(year)
            except (TypeError, ValueError):
                return JsonResponse({'success': False, 'message': 'year must be an integer.'}, status=400)
        
        if report_type in [2, 3, 4]:
            month = request.GET.get('month')
            if not month:
                return JsonResponse({'success': False, 'message': 'month is required for monthly reports.'}, status=400)
            try:
                month = int(month)
                if not 1 <= month <= 12:
                    return JsonResponse({'success': False, 'message': 'month must be between 1-12.'}, status=400)
            except (TypeError, ValueError):
                return JsonResponse({'success': False, 'message': 'month must be an integer.'}, status=400)
        
        if report_type == 8:
            month = request.GET.get('month')
            if month:
                try:
                    month = int(month)
                    if not 1 <= month <= 12:
                        return JsonResponse({'success': False, 'message': 'month must be between 1-12.'}, status=400)
                except (TypeError, ValueError):
                    return JsonResponse({'success': False, 'message': 'month must be an integer.'}, status=400)
            else:
                month = None

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
            service = ChildReportService(repo, reports_query=reports_query, pdf_generator=PdfGenerator())

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

            # Route to appropriate report generation method
            if report_type == 1:
                result = service.generate_child_summary_pdf(
                    child_id,
                    header_lines=header_lines,
                    watermark=watermark_param,
                    left_image=left_image_param,
                    right_image=right_image_param,
                    generated_by_name=gen_name,
                    generated_by_role=gen_role,
                )
                # Child summary returns (pdf_bytes, missing_fields, filename)
                pdf_bytes = result[0]
                missing_fields = result[1] if len(result) > 1 else []
                filename = result[2] if len(result) > 2 else f"child_summary_{child_id}.pdf"
            
            elif report_type == 2:
                result = service.generate_monthly_immunization_coverage_pdf(
                    year, month,
                    header_lines=header_lines,
                    watermark=watermark_param,
                    left_image=left_image_param,
                    right_image=right_image_param,
                    generated_by_name=gen_name,
                    generated_by_role=gen_role,
                )
                pdf_bytes = result[0]
                filename = result[1]
                missing_fields = []
            
            elif report_type == 3:
                result = service.generate_monthly_visit_completion_pdf(
                    year, month,
                    header_lines=header_lines,
                    watermark=watermark_param,
                    left_image=left_image_param,
                    right_image=right_image_param,
                    generated_by_name=gen_name,
                    generated_by_role=gen_role,
                )
                pdf_bytes = result[0]
                filename = result[1]
                missing_fields = []
            
            elif report_type == 4:
                result = service.generate_monthly_growth_nutrition_pdf(
                    year, month,
                    header_lines=header_lines,
                    watermark=watermark_param,
                    left_image=left_image_param,
                    right_image=right_image_param,
                    generated_by_name=gen_name,
                    generated_by_role=gen_role,
                )
                pdf_bytes = result[0]
                filename = result[1]
                missing_fields = []
            
            elif report_type == 5:
                result = service.generate_annual_screening_risk_pdf(
                    year,
                    header_lines=header_lines,
                    watermark=watermark_param,
                    left_image=left_image_param,
                    right_image=right_image_param,
                    generated_by_name=gen_name,
                    generated_by_role=gen_role,
                )
                pdf_bytes = result[0]
                filename = result[1]
                missing_fields = []
            
            elif report_type == 6:
                result = service.generate_annual_immunization_performance_pdf(
                    year,
                    header_lines=header_lines,
                    watermark=watermark_param,
                    left_image=left_image_param,
                    right_image=right_image_param,
                    generated_by_name=gen_name,
                    generated_by_role=gen_role,
                )
                pdf_bytes = result[0]
                filename = result[1]
                missing_fields = []
            
            elif report_type == 7:
                result = service.generate_annual_growth_development_pdf(
                    year,
                    header_lines=header_lines,
                    watermark=watermark_param,
                    left_image=left_image_param,
                    right_image=right_image_param,
                    generated_by_name=gen_name,
                    generated_by_role=gen_role,
                )
                pdf_bytes = result[0]
                filename = result[1]
                missing_fields = []
            
            elif report_type == 8:
                result = service.generate_all_analytics_reports_pdf(
                    year, month,
                    header_lines=header_lines,
                    watermark=watermark_param,
                    left_image=left_image_param,
                    right_image=right_image_param,
                    generated_by_name=gen_name,
                    generated_by_role=gen_role,
                )
                pdf_bytes = result[0]
                filename = result[1]
                missing_fields = []

            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            if missing_fields:
                # Expose a simple CSV of missing fields so clients can surface
                # a helpful message (also logged server-side).
                try:
                    response['X-Report-Missing-Fields'] = ', '.join(missing_fields)
                    logger.warning('Child report generated with missing fields: %s', response['X-Report-Missing-Fields'])
                except Exception:
                    logger.exception('Failed to set missing-fields header')
            return response
        except GenericChildHealthRecordException as chre:
            return JsonResponse({'success': False, 'message': str(chre)}, status=404)
        except Exception:
            logger.exception('Failed generating child report (type=%s)', report_type)
            return JsonResponse({'success': False, 'message': 'Failed to generate report.'}, status=500)
