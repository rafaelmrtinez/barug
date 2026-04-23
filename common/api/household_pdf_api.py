# -------------------------------
# HOUSEHOLD PDF GENERATION
# -------------------------------

import logging
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required
from dependency_injector.wiring import inject, Provide

from authentication.guards import session_login_required, role_required
from src.app.bootstrap.app_containers import AppContainer
from src.app.contracts.household_service_contract import IHouseholdService
from src.app.services.household_report_service import HouseholdReportService
from src.infra.utilities.pdf_generator_h import PdfGeneratorH

logger = logging.getLogger(__name__)
authorized_role = (
    "Barangay Secretary", "BARANGAY SECRETARY", "barangay secretary",
    "Barangay Captain", "BARANGAY CAPTAIN", "barangay captain",
    "Barangay Health Worker", "BARANGAY HEALTH WORKER", "bhw", "Super Admin"
)

@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*authorized_role), name="dispatch")
@method_decorator(csrf_required, name="dispatch")
class HouseholdPDFAPI(View):
    """Generate PDF report for household list with current filters.
    
    Query params:
      - search: string (optional) -- search term
      - house_type: string (optional) -- house type filter
      - house_ownership: string (optional) -- house ownership filter
    """
    
    @inject
    def get(self, request: HttpRequest, household_service: IHouseholdService = Provide[AppContainer.household_service]):
        try:
            # Get filter parameters
            search = request.GET.get('search')
            house_type = request.GET.get('house_type')
            house_ownership = request.GET.get('house_ownership')
            
            # Convert string parameters to int if provided
            house_type_int = int(house_type) if house_type else None
            house_ownership_int = int(house_ownership) if house_ownership else None
            
            # Get filtered household data
            rows = household_service.execute(
                search=search,
                house_type=house_type_int,
                ownership_type=house_ownership_int,
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
            service = HouseholdReportService(pdf_generator=PdfGeneratorH())
            pdf_bytes, filename = service.generate_household_list_pdf(
                household_data=rows,
                search_term=search,
                house_type=house_type,
                house_ownership=house_ownership,
                generated_by_name=gen_name,
                generated_by_role=gen_role,
            )
            
            # Create response
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            
            return response
            
        except Exception as e:
            logger.exception('Failed generating household PDF')
            return JsonResponse({'success': False, 'message': 'Failed to generate PDF report.'}, status=500)