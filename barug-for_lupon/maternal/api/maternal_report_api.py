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
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException
from src.infra.repositories.maternal_report_repository import MaternalReportRepository
from src.app.services.maternal_report_service import MaternalReportService
from src.infra.utilities.pdf_generator import PdfGenerator

logger = logging.getLogger(__name__)

ALLOWED_ROLES = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")


@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*ALLOWED_ROLES), name="dispatch")
@method_decorator(csrf_required, name="dispatch")
class MaternalReportAPI(View):
    """Generate Maternal Health Reports based on report type.

    Query params:
      - report_type: integer (optional, default=1)
        1 = Maternal Summary Report (requires mhr_id)
        2 = Monthly Visit Compliance (requires year, month)
        3 = Monthly Risk Indicator Summary (requires year, month)
        4 = Monthly Immunization & Supplement Adherence (requires year, month)
        5 = Trimester Health Outcome Trajectory (requires year, trimester)
        6 = Trimester Complication & Referral Analytics (requires year, trimester)
        7 = Trimester Service Utilization (requires year, trimester)
        8 = Annual Maternal Outcome Consolidated (requires year)
        9 = Annual Coverage Scorecard (requires year)
        10 = Annual Trend Analysis (requires year)
        11 = All-in-One Analytics (requires year, month)
      - mhr_id: integer (required for report_type=1)
      - year: integer (required for report_type 2-11)
      - month: integer (required for report_type 2-4, 11)
      - trimester: integer (required for report_type 5-7, must be 1-3)
    """

    @inject
    def get(self, request: HttpRequest, repo: MaternalReportRepository = Provide[app.infra.maternal_report_repository], *args, **kwargs):
        # Determine report type (default to 1 for backward compatibility)
        report_type = request.GET.get('report_type', '1')
        try:
            report_type = int(report_type)
            if report_type not in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]:
                return JsonResponse({'success': False, 'message': 'Invalid report_type. Must be 1-11.'}, status=400)
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'message': 'report_type must be an integer (1-11).'}, status=400)

        # Resolve repository provider; fallback to container factory or direct construction
        try:
            if not hasattr(repo, 'assemble_report_payload'):
                try:
                    # try resolving from container provider if available
                    repo = app.infra.maternal_report_repository()
                except Exception:
                    repo = MaternalReportRepository(ConnectionAdapter())
        except Exception:
            logger.exception('Error resolving maternal_report_repository provider')
            return JsonResponse({'success': False, 'message': 'Unexpected server error.'}, status=500)

        # Resolve reports query for analytics reports (types 2-11)
        reports_query = None
        if report_type in [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]:
            try:
                if hasattr(app, 'infra') and hasattr(app.infra, 'maternal_reports_query'):
                    try:
                        reports_query = app.infra.maternal_reports_query()
                    except Exception:
                        from src.infra.repositories.queries.maternal_reports_query import MaternalReportsQuery
                        reports_query = MaternalReportsQuery(ConnectionAdapter())
                else:
                    from src.infra.repositories.queries.maternal_reports_query import MaternalReportsQuery
                    reports_query = MaternalReportsQuery(ConnectionAdapter())
            except Exception:
                logger.exception('Error resolving maternal_reports_query provider')
                return JsonResponse({'success': False, 'message': 'Unexpected server error.'}, status=500)

        # Validate required parameters based on report type
        if report_type == 1:
            mhr_id = request.GET.get('mhr_id')
            if not mhr_id:
                return JsonResponse({'success': False, 'message': 'mhr_id is required for report_type=1.'}, status=400)
            try:
                mhr_id = int(mhr_id)
            except (TypeError, ValueError):
                return JsonResponse({'success': False, 'message': 'mhr_id must be an integer.'}, status=400)
        
        if report_type in [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]:
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
        
        if report_type in [5, 6, 7]:
            trimester = request.GET.get('trimester')
            if not trimester:
                return JsonResponse({'success': False, 'message': 'trimester is required for trimester reports.'}, status=400)
            try:
                trimester = int(trimester)
                if not 1 <= trimester <= 3:
                    return JsonResponse({'success': False, 'message': 'trimester must be between 1-3.'}, status=400)
            except (TypeError, ValueError):
                return JsonResponse({'success': False, 'message': 'trimester must be an integer.'}, status=400)
        
        if report_type == 11:
            month = request.GET.get('month')
            if not month:
                return JsonResponse({'success': False, 'message': 'month is required for all-in-one analytics report.'}, status=400)
            try:
                month = int(month)
                if not 1 <= month <= 12:
                    return JsonResponse({'success': False, 'message': 'month must be between 1-12.'}, status=400)
            except (TypeError, ValueError):
                return JsonResponse({'success': False, 'message': 'month must be an integer.'}, status=400)

        # Parse optional header overrides from query params
        header_lines_param = request.GET.get('header_lines')
        watermark_param = request.GET.get('watermark')
        left_image_param = request.GET.get('left_image')
        right_image_param = request.GET.get('right_image')

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

        # Set default logo if none provided
        if not left_image_param and not right_image_param:
            try:
                # if no images provided, set a default left logo
                default_logo_path = os.path.join(BASE_DIR, 'static', 'images', 'brgy-sto-nino.png')
                if os.path.exists(default_logo_path):
                    left_image_param = default_logo_path
            except Exception:
                logger.exception('Error resolving default logo path')
                left_image_param = None

        # Construct service (inject PdfGenerator and reports_query)
        try:
            service = MaternalReportService(repo, pdf_generator=PdfGenerator(), reports_query=reports_query)
            
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

            # Route to appropriate report generation method based on report_type
            if report_type == 1:
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
                pdf_bytes = result[0] if isinstance(result, (tuple, list)) else result
                filename = result[1] if isinstance(result, (tuple, list)) and len(result) >= 2 else f"maternal_summary_{mhr_id}.pdf"
            
            elif report_type == 2:
                result = service.generate_monthly_visit_compliance_pdf(
                    year,
                    month,
                    header_lines=header_lines,
                    watermark=watermark_param,
                    left_image=left_image_param,
                    right_image=right_image_param,
                )
                pdf_bytes = result[0]
                filename = result[1]
            
            elif report_type == 3:
                result = service.generate_monthly_risk_indicator_pdf(
                    year,
                    month,
                    header_lines=header_lines,
                    watermark=watermark_param,
                    left_image=left_image_param,
                    right_image=right_image_param,
                )
                pdf_bytes = result[0]
                filename = result[1]
            
            elif report_type == 4:
                result = service.generate_monthly_immunization_supplement_pdf(
                    year,
                    month,
                    header_lines=header_lines,
                    watermark=watermark_param,
                    left_image=left_image_param,
                    right_image=right_image_param,
                )
                pdf_bytes = result[0]
                filename = result[1]
            
            elif report_type == 5:
                result = service.generate_trimester_health_outcome_pdf(
                    year,
                    trimester,
                    header_lines=header_lines,
                    watermark=watermark_param,
                    left_image=left_image_param,
                    right_image=right_image_param,
                )
                pdf_bytes = result[0]
                filename = result[1]
            
            elif report_type == 6:
                result = service.generate_trimester_complication_referral_pdf(
                    year,
                    trimester,
                    header_lines=header_lines,
                    watermark=watermark_param,
                    left_image=left_image_param,
                    right_image=right_image_param,
                )
                pdf_bytes = result[0]
                filename = result[1]
            
            elif report_type == 7:
                result = service.generate_trimester_service_utilization_pdf(
                    year,
                    trimester,
                    header_lines=header_lines,
                    watermark=watermark_param,
                    left_image=left_image_param,
                    right_image=right_image_param,
                )
                pdf_bytes = result[0]
                filename = result[1]
            
            elif report_type == 8:
                result = service.generate_annual_outcome_consolidated_pdf(
                    year,
                    header_lines=header_lines,
                    watermark=watermark_param,
                    left_image=left_image_param,
                    right_image=right_image_param,
                )
                pdf_bytes = result[0]
                filename = result[1]
            
            elif report_type == 9:
                result = service.generate_annual_coverage_scorecard_pdf(
                    year,
                    header_lines=header_lines,
                    watermark=watermark_param,
                    left_image=left_image_param,
                    right_image=right_image_param,
                )
                pdf_bytes = result[0]
                filename = result[1]
            
            elif report_type == 10:
                result = service.generate_annual_trend_analysis_pdf(
                    year,
                    header_lines=header_lines,
                    watermark=watermark_param,
                    left_image=left_image_param,
                    right_image=right_image_param,
                )
                pdf_bytes = result[0]
                filename = result[1]
            
            elif report_type == 11:
                result = service.generate_all_analytics_reports_pdf(
                    year,
                    month,
                    header_lines=header_lines,
                    watermark=watermark_param,
                    left_image=left_image_param,
                    right_image=right_image_param,
                )
                pdf_bytes = result[0]
                filename = result[1]

            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            return response
        except MaternalHealthRecordException as mhe:
            return JsonResponse({'success': False, 'message': str(mhe)}, status=404)
        except Exception:
            logger.exception('Failed generating maternal report (type=%s)', report_type)
            return JsonResponse({'success': False, 'message': 'Failed to generate report.'}, status=500)
