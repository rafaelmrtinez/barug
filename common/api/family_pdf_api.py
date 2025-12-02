# -------------------------------
# FAMILY PDF GENERATION
# -------------------------------

import logging
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required
from dependency_injector.wiring import inject, Provide

from authentication.guards import session_login_required, role_required
from src.app.bootstrap.app_containers import AppContainer
from src.domain.contracts.household_repository_contract import IHouseholdRepository
from src.app.services.family_report_service import FamilyReportService
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
class FamilyPDFAPI(View):
    """Generate PDF report for family list with current filters.
    
    Query params:
      - search: string (optional) -- search term
      - household_type: string (optional) -- household type filter
      - nhts_status: string (optional) -- NHTS status filter
      - indigent_status: string (optional) -- indigent status filter
    """
    
    @inject
    def get(self, request: HttpRequest, household_repo: IHouseholdRepository = Provide[AppContainer.household_repository]):
        try:
            # Get filter parameters
            search = request.GET.get('search')
            household_type = request.GET.get('household_type')
            nhts_status = request.GET.get('nhts_status')
            indigent_status = request.GET.get('indigent_status')
            
            # Convert string parameters to int if provided
            household_type_int = int(household_type) if household_type else None
            nhts_status_int = int(nhts_status) if nhts_status else None
            indigent_status_int = int(indigent_status) if indigent_status else None
            
            # Get filtered family data
            if search:
                rows = household_repo.search_family(search)
            elif household_type_int:
                rows = household_repo.filter_family_by_household_type(household_type_int)
            elif nhts_status_int:
                rows = household_repo.filter_family_by_nhts_status(nhts_status_int)
            elif indigent_status_int:
                rows = household_repo.filter_family_by_indigent_status(indigent_status_int)
            else:
                rows = household_repo.fetch_family_list()
            
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
            service = FamilyReportService(pdf_generator=PdfGeneratorH())
            pdf_bytes, filename = service.generate_family_list_pdf(
                family_data=rows,
                search_term=search,
                household_type=household_type,
                nhts_status=nhts_status,
                indigent_status=indigent_status,
                generated_by_name=gen_name,
                generated_by_role=gen_role,
            )
            
            # Create response
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            
            return response
            
        except Exception as e:
            logger.exception('Failed generating family PDF')
            return JsonResponse({'success': False, 'message': 'Failed to generate PDF report.'}, status=500)
