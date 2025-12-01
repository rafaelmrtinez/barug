# common/api/household_history_pdf_api.py
"""
API endpoint for generating household history PDF reports.
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
from src.app.services.household_history_report_service import HouseholdHistoryReportService

logger = logging.getLogger(__name__)

# BHW Role
ROLE_BHW = ("BARANGAY HEALTH WORKER", "Barangay Health Worker", "bhw", "Super Admin")


def _to_int_or_none(val):
    """Convert value to int or return None"""
    if val is None or val == '':
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


@method_decorator(session_login_required, name='dispatch')
@method_decorator(role_required(*ROLE_BHW), name='dispatch')
@method_decorator(nocache, name='dispatch')
class HouseholdHistoryPDFAPI(View):
    """
    API View to generate PDF reports for household history.
    """

    @inject
    def get(
        self,
        request: HttpRequest,
        household_repo: IHouseholdRepository = Provide[AppContainer.household_repository],
    ) -> HttpResponse:
        """
        Generate PDF for household history based on query parameters.
        
        Query params:
        - quarter: Quarter (1-4, required)
        - year: Year (required)
        - search: Search term (optional)
        - house_type: House type ID (optional)
        - house_ownership: House ownership ID (optional)
        """
        try:
            # Get filter parameters
            quarter = _to_int_or_none(request.GET.get("quarter"))
            year = _to_int_or_none(request.GET.get("year"))
            
            if not quarter or not year:
                return HttpResponseBadRequest("Quarter and year are required")
            
            search = request.GET.get("search")
            house_type = _to_int_or_none(request.GET.get("house_type"))
            house_ownership = _to_int_or_none(request.GET.get("house_ownership"))
            
            # Fetch data based on filters
            if search:
                rows = household_repo.search_household_history(search, quarter, year)
            elif house_type:
                rows = household_repo.sort_household_history_by_house_type(house_type, quarter, year)
            elif house_ownership:
                rows = household_repo.sort_household_history_by_ownership(house_ownership, quarter, year)
            else:
                rows = household_repo.fetch_household_history_by_quarter_year(quarter, year)
            
            # Get user info from session
            user_name = request.session.get("authenticated_display_name", "Unknown User")
            user_role = request.session.get("authenticated_role_name", "Secretary")
            
            # Get filter labels
            house_type_label = None
            house_ownership_label = None
            
            if house_type:
                type_labels = {
                    1: "CONCRETE",
                    2: "SEMI-CONCRETE",
                    3: "LIGHT MATERIAL",
                }
                house_type_label = type_labels.get(house_type)
            
            if house_ownership:
                ownership_labels = {
                    1: "OWNED",
                    2: "RENTED",
                    3: "FAMILY-OWNED",
                    4: "GOVERNMENT HOUSING",
                    5: "INFORMAL SETTLER",
                }
                house_ownership_label = ownership_labels.get(house_ownership)
            
            # Generate PDF
            service = HouseholdHistoryReportService()
            pdf_bytes, filename = service.generate_household_history_pdf(
                household_data=rows,
                quarter=quarter,
                year=year,
                search_term=search,
                house_type=house_type_label,
                house_ownership=house_ownership_label,
                generated_by_name=user_name,
                generated_by_role=user_role,
            )
            
            response = HttpResponse(pdf_bytes, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response
            
        except Exception as e:
            logger.exception("Error generating household history PDF")
            return HttpResponseBadRequest(f"Error generating PDF: {str(e)}")
