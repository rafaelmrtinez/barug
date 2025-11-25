# -------------------------------
# FINANCIAL REPORT PDF GENERATION
# -------------------------------

import logging
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required
from dependency_injector.wiring import inject, Provide

from authentication.guards import session_login_required, role_required
from src.app.bootstrap.app_containers import AppContainer
from src.app.services.or_service import IORService
from src.app.services.financial_report_service import FinancialReportService
from src.infra.utilities.pdf_generator_h import PdfGeneratorH

logger = logging.getLogger(__name__)
authorized_role = "Barangay Treasurer", "BARANGAY TREASURER", "barangay treasurer", "Barangay Captain", "BARANGAY CAPTAIN", "barangay captain"

@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*authorized_role), name="dispatch")
@method_decorator(csrf_required, name="dispatch")
class FinancialPDFAPI(View):
    """Generate PDF report for financial report with current filters.
    
    Query params:
      - search: string (optional) -- search term
      - pay_meth: string (optional) -- payment method filter
    """
    
    @inject
    def get(self, request: HttpRequest, or_service: IORService = Provide[AppContainer.or_service]):
        try:
            # Get filter parameters
            search = request.GET.get('search')
            pay_meth = request.GET.get('pay_meth')
            
            # Convert payment method to int if provided
            payment_method = int(pay_meth) if pay_meth else None
            
            # Get filtered OR data
            rows = or_service.execute(
                search=search,
                payment_method=payment_method,
            )
            
            # Get user info for signature
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
            
            # Generate PDF using ReportLab
            service = FinancialReportService(pdf_generator=PdfGeneratorH())
            pdf_bytes, filename = service.generate_financial_report_pdf(
                or_data=rows,
                search_term=search,
                payment_method=pay_meth,
                generated_by_name=gen_name,
                generated_by_role=gen_role,
            )
            
            # Create response
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            
            return response
            
        except Exception as e:
            logger.exception('Failed generating financial report PDF')
            return JsonResponse({'success': False, 'message': 'Failed to generate PDF report.'}, status=500)