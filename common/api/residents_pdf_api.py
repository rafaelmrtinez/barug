# -------------------------------
# RESIDENTS PDF GENERATION
# -------------------------------

import logging
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required
from dependency_injector.wiring import inject, Provide

from authentication.guards import session_login_required, role_required
from src.app.bootstrap.app_containers import AppContainer
from src.app.contracts.resident_service_contract import IResidentService
from src.app.services.resident_report_service import ResidentReportService
from src.infra.utilities.pdf_generator_h import PdfGeneratorH

logger = logging.getLogger(__name__)
SECRETARY_ROLE = "Barangay Secretary", "BARANGAY SECRETARY", "barangay secretary"

@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*SECRETARY_ROLE), name="dispatch")
@method_decorator(csrf_required, name="dispatch")
class ResidentsPDFAPI(View):
    """Generate PDF report for residents list with current filters.
    
    Query params:
      - search: string (optional) -- search term
      - purok_sitio: string (optional) -- purok/sitio filter
    """
    
    @inject
    def get(self, request: HttpRequest, resident_service: IResidentService = Provide[AppContainer.resident_service]):
        try:
            # Get filter parameters
            search = request.GET.get('search')
            purok_sitio = request.GET.get('purok_sitio')
            
            # Get filtered residents data
            rows = resident_service.execute(
                search=search,
                purok=purok_sitio,
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
            service = ResidentReportService(pdf_generator=PdfGeneratorH())
            pdf_bytes, filename = service.generate_residents_list_pdf(
                residents_data=rows,
                search_term=search,
                purok_sitio=purok_sitio,
                generated_by_name=gen_name,
                generated_by_role=gen_role,
            )
            
            # Create response
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            
            return response
            
        except Exception as e:
            logger.exception('Failed generating residents PDF')
            return JsonResponse({'success': False, 'message': 'Failed to generate PDF report.'}, status=500)
        