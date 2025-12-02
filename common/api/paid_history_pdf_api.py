from django.http import HttpResponse, JsonResponse, HttpRequest
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from typing import Optional
from datetime import datetime, timedelta
import logging

from authentication.guards import role_required, session_login_required
from dependency_injector.wiring import inject, Provide
from barug.containers import AppContainer

from src.app.services.paid_history_report_service import PaidHistoryReportService
from src.infra.utilities.pdf_generator_h import PdfGeneratorH

logger = logging.getLogger(__name__)

# Roles that can generate paid history PDFs (same as business detail PDF)
authorized_role = "Barangay Secretary", "BARANGAY SECRETARY", "barangay secretary", "Barangay Captain", "BARANGAY CAPTAIN", "barangay captain", "Barangay Clerk", "BARANGAY CLERK", "barangay clerk"

@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*authorized_role), name="dispatch")
@method_decorator(csrf_exempt, name="dispatch")  # GET request, no CSRF needed
class PaidHistoryPDFAPI(View):
    """Generate PDF report for business paid history with filters.
    
    URL params:
      - b_id: int (required) -- business ID
    
    Query params:
      - date_range: str (optional) -- 'all', '30', '90', '180', '365', 'custom'
      - from_date: str (optional) -- YYYY-MM-DD format
      - to_date: str (optional) -- YYYY-MM-DD format
      - year: int (optional) -- filter by specific year
      - sort_order: str (optional) -- 'asc' or 'desc' (default: 'desc')
    """
    
    @inject
    def get(
        self, 
        request: HttpRequest, 
        b_id: int,
        business_info = Provide[AppContainer.owner_business_service]
    ):
        try:
            # Get business details
            dto = business_info.execute_by_business_id(b_id)
            
            if not dto or not dto.business:
                return JsonResponse({'success': False, 'message': f'Business #{b_id} not found.'}, status=404)
            
            # Get filter parameters
            date_range = request.GET.get('date_range', 'all')
            from_date = request.GET.get('from_date')
            to_date = request.GET.get('to_date')
            year = request.GET.get('year')
            sort_order = request.GET.get('sort_order', 'desc')
            
            # Calculate date range
            from_date_obj = None
            to_date_obj = None
            
            if date_range == 'custom' and from_date and to_date:
                try:
                    from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
                    to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
                except Exception:
                    pass
            elif date_range != 'all':
                try:
                    days = int(date_range)
                    to_date_obj = datetime.now().date()
                    from_date_obj = to_date_obj - timedelta(days=days)
                except Exception:
                    pass
            
            # Get paid history data directly from repository via AppContainer
            from barug.containers import app
            quote_repo = app.infra.business_renewal_quote()
            paid_rows = quote_repo.fetch_paid_history(b_id)
            
            # Apply filters
            filtered_rows = []
            for row in paid_rows:
                # Year filter
                if year and str(row.get('period_year')) != year:
                    continue
                
                # Date range filter
                if from_date_obj and to_date_obj and row.get('paid_on'):
                    try:
                        paid_date = row['paid_on']
                        if isinstance(paid_date, str):
                            paid_date = datetime.strptime(paid_date.split('T')[0], '%Y-%m-%d').date()
                        if not (from_date_obj <= paid_date <= to_date_obj):
                            continue
                    except Exception:
                        continue
                
                filtered_rows.append(row)
            
            # Sort
            reverse = (sort_order == 'desc')
            filtered_rows.sort(key=lambda x: x.get('period_year', 0), reverse=reverse)
            
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
            service = PaidHistoryReportService(pdf_generator=PdfGeneratorH())
            pdf_bytes, filename = service.generate_paid_history_pdf(
                business_dto=dto,
                paid_rows=filtered_rows,
                from_date=from_date_obj,
                to_date=to_date_obj,
                year_filter=year,
                generated_by_name=gen_name,
                generated_by_role=gen_role,
            )
            
            # Create response
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            
            return response
            
        except Exception as e:
            logger.exception(f"Failed to generate paid history PDF for business {b_id}")
            return JsonResponse({
                'success': False,
                'message': f'Failed to generate PDF: {str(e)}'
            }, status=500)
