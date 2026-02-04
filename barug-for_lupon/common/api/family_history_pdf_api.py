# common/api/family_history_pdf_api.py
"""
API endpoint for generating family history PDF reports.
"""

import logging
from typing import Optional
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.views import View
from django.utils.decorators import method_decorator
from dependency_injector.wiring import inject, Provide

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from src.app.bootstrap.app_containers import AppContainer
from src.domain.contracts.household_repository_contract import IHouseholdRepository
from src.app.services.family_history_report_service import FamilyHistoryReportService

logger = logging.getLogger(__name__)

# Authorized roles
AUTHORIZED_ROLES = (
    "BARANGAY HEALTH WORKER", "Barangay Health Worker", "bhw",
    "Barangay Secretary", "BARANGAY SECRETARY", "barangay secretary",
    "Barangay Captain", "BARANGAY CAPTAIN", "barangay captain",
    "Super Admin"
)


def _to_int_or_none(val):
    """Convert value to int or return None"""
    if val is None or val == '':
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


@method_decorator(session_login_required, name='dispatch')
@method_decorator(role_required(*AUTHORIZED_ROLES), name='dispatch')
@method_decorator(nocache, name='dispatch')
class FamilyHistoryPDFAPI(View):
    """
    API View to generate PDF reports for family history.
    """

    @inject
    def get(
        self,
        request: HttpRequest,
        household_repo: IHouseholdRepository = Provide[AppContainer.household_repository],
    ) -> HttpResponse:
        """
        Generate PDF for family history based on query parameters.
        
        Query params:
        - quarter: Quarter (1-4, required)
        - year: Year (required)
        - search: Search term (optional)
        - household_type: Household type ID (optional)
        - nhts_status: NHTS status ID (optional)
        - indigent_status: Indigent status ID (optional)
        """
        try:
            # Get filter parameters
            quarter = _to_int_or_none(request.GET.get("quarter"))
            year = _to_int_or_none(request.GET.get("year"))
            
            if not quarter or not year:
                return HttpResponseBadRequest("Quarter and year are required")
            
            search = request.GET.get("search")
            household_type = _to_int_or_none(request.GET.get("household_type"))
            nhts_status = _to_int_or_none(request.GET.get("nhts_status"))
            indigent_status = _to_int_or_none(request.GET.get("indigent_status"))
            
            # Fetch data based on filters
            if search:
                rows = household_repo.search_family_history(search, quarter, year)
            elif household_type:
                rows = household_repo.sort_family_history_by_household_type(household_type, quarter, year)
            elif nhts_status:
                rows = household_repo.sort_family_history_by_nhts_status(nhts_status, quarter, year)
            elif indigent_status:
                rows = household_repo.sort_family_history_by_indigent_status(indigent_status, quarter, year)
            else:
                rows = household_repo.fetch_family_history_by_quarter_year(quarter, year)
            
            # Get user info from session
            user_name = request.session.get("authenticated_display_name", "Unknown User")
            user_role = request.session.get("authenticated_role_name", "Secretary")
            
            # Get filter labels
            household_type_label = None
            nhts_status_label = None
            indigent_status_label = None
            
            if household_type:
                type_labels = {
                    1: "CONCRETE",
                    2: "SEMI-CONCRETE",
                    3: "LIGHT MATERIAL",
                }
                household_type_label = type_labels.get(household_type)
            
            if nhts_status:
                nhts_labels = {
                    1: "MEMBER",
                    2: "NON-MEMBER",
                }
                nhts_status_label = nhts_labels.get(nhts_status)
            
            if indigent_status:
                indigent_labels = {
                    1: "INDIGENT",
                    2: "NON-INDIGENT",
                }
                indigent_status_label = indigent_labels.get(indigent_status)
            
            # Generate PDF
            service = FamilyHistoryReportService()
            pdf_bytes, filename = service.generate_family_history_pdf(
                family_data=rows,
                quarter=quarter,
                year=year,
                search_term=search,
                household_type=household_type_label,
                nhts_status=nhts_status_label,
                indigent_status=indigent_status_label,
                generated_by_name=user_name,
                generated_by_role=user_role,
            )
            
            response = HttpResponse(pdf_bytes, content_type="application/pdf")
            response["Content-Disposition"] = f'inline; filename="{filename}"'
            return response
            
        except Exception as e:
            logger.exception("Error generating family history PDF")
            return HttpResponseBadRequest(f"Error generating PDF: {str(e)}")
