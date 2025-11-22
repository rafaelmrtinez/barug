# -------------------------------
# BUSINESS PDF GENERATION
# -------------------------------

import logging
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required
from dependency_injector.wiring import inject, Provide

from authentication.guards import session_login_required, role_required
from src.app.bootstrap.app_containers import AppContainer
from src.app.contracts.business_service_contract import IBusinessService
from src.app.services.business_report_service import BusinessReportService
from src.infra.utilities.pdf_generator_h import PdfGeneratorH

logger = logging.getLogger(__name__)
authorized_role = "Barangay Secretary", "BARANGAY SECRETARY", "barangay secretary", "Barangay Captain", "BARANGAY CAPTAIN", "barangay captain", "Barangay Clerk", "BARANGAY CLERK", "barangay clerk"

@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*authorized_role), name="dispatch")
@method_decorator(csrf_required, name="dispatch")
class BusinessPDFAPI(View):
    """Generate PDF report for business list with current filters.
    
    Query params:
      - search: string (optional) -- search term
      - b_category: string (optional) -- business category filter
      - ownership_type: string (optional) -- ownership type filter
      - status: string (optional) -- status filter
    """
    
    @inject
    def get(self, request: HttpRequest, business_service: IBusinessService = Provide[AppContainer.business_service]):
        try:
            # Get filter parameters
            search = request.GET.get('search')
            b_category = request.GET.get('b_category')
            ownership_type = request.GET.get('ownership_type')
            status = request.GET.get('status')
            
            # Convert string parameters to int if provided
            b_category_int = int(b_category) if b_category else None
            ownership_type_int = int(ownership_type) if ownership_type else None
            status_int = int(status) if status else None
            
            # Get filtered business data
            rows = business_service.execute(
                search=search,
                b_category=b_category_int,
                ownership_type=ownership_type_int,
                status=status_int,
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
            service = BusinessReportService(pdf_generator=PdfGeneratorH())
            pdf_bytes, filename = service.generate_business_list_pdf(
                business_data=rows,
                search_term=search,
                b_category=b_category,
                ownership_type=ownership_type,
                status=status,
                generated_by_name=gen_name,
                generated_by_role=gen_role,
            )
            
            # Create response
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            
            return response
            
        except Exception as e:
            logger.exception('Failed generating business PDF')
            return JsonResponse({'success': False, 'message': 'Failed to generate PDF report.'}, status=500)