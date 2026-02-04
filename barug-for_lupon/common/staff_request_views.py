"""
Modernized Staff Request Views for All Roles
============================================
This module provides unified staff request management functionality
for secretary, midwife, lupon_pres, and captain roles.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
import json
from typing import Dict, List, Any, Optional


class StaffRequestMixin:
    """Mixin providing common staff request functionality for all roles."""
    
    def get_role_context(self) -> Dict[str, str]:
        """Get role-specific context for templates."""
        role_mapping = {
            'secretary': {
                'app_name': 'secretary',
                'list_url': 'secretary:staff_requests_list',
                'detail_url': 'secretary:staff_request_detail',
                'create_url': 'secretary:staff_selection_non-resident',
                'template_base': 'secretary/staff/'
            },
            'captain': {
                'app_name': 'captain',
                'list_url': 'captain:staff_requests_list',
                'detail_url': 'captain:staff_request_detail',
                'create_url': 'captain:staff_selection_non-resident',
                'template_base': 'captain/'
            },
            'midwife': {
                'app_name': 'midwife',
                'list_url': 'midwife:staff_requests_list',
                'detail_url': 'midwife:staff_request_detail',
                'create_url': 'midwife:staff_selection_non-resident',
                'template_base': 'midwife/acc_management/'
            },
            'lupon_pres': {
                'app_name': 'lupon_pres',
                'list_url': 'lupon_pres:staff_requests_list',
                'detail_url': 'lupon_pres:staff_request_detail',
                'create_url': 'lupon_pres:staff_selection_non-resident',
                'template_base': 'lupon_pres/members/'
            }
        }
        return role_mapping.get(self.role, role_mapping['secretary'])

    def execute_sql_function(self, function_name: str, params: List[Any] = None) -> List[Dict]:
        """Execute SQL function and return results as list of dictionaries."""
        if params is None:
            params = []
        
        with connection.cursor() as cursor:
            placeholders = ', '.join(['%s'] * len(params))
            query = f"SELECT * FROM {function_name}({placeholders})"
            cursor.execute(query, params)
            
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_request_statistics(self) -> Dict[str, int]:
        """Get request statistics for dashboard."""
        try:
            stats = self.execute_sql_function('get_staff_request_statistics')
            return stats[0] if stats else {
                'total_requests': 0,
                'pending_requests': 0,
                'approved_requests': 0,
                'rejected_requests': 0,
                'completed_requests': 0
            }
        except Exception as e:
            print(f"Error getting statistics: {e}")
            return {
                'total_requests': 0,
                'pending_requests': 0,
                'approved_requests': 0,
                'rejected_requests': 0,
                'completed_requests': 0
            }


class StaffRequestListView(StaffRequestMixin, View):
    """Unified staff request list view for all roles."""
    
    def __init__(self, role: str):
        self.role = role
        super().__init__()

    @method_decorator(login_required)
    def get(self, request):
        """Handle GET request for staff request list."""
        try:
            # Get query parameters
            page = request.GET.get('page', 1)
            search = request.GET.get('search', '').strip()
            role_filter = request.GET.get('role_filter', '')
            status_filter = request.GET.get('status_filter', '')
            
            # Convert parameters
            try:
                page = int(page)
            except (ValueError, TypeError):
                page = 1
                
            try:
                status_filter_int = int(status_filter) if status_filter else None
            except (ValueError, TypeError):
                status_filter_int = None
            
            # Pagination settings
            per_page = 20
            offset = (page - 1) * per_page
            
            # Get requests using SQL function
            params = [
                role_filter if role_filter else None,
                status_filter_int,
                per_page + 1,  # Get one extra to check if there are more pages
                offset,
                search if search else None
            ]
            
            requests_data = self.execute_sql_function('get_staff_requests_list', params)
            
            # Check if there are more pages
            has_next = len(requests_data) > per_page
            if has_next:
                requests_data = requests_data[:per_page]
            
            # Add progress information to each request
            for request_item in requests_data:
                request_item['progress'] = {
                    'progress_percent': request_item.get('progress_percent', 0),
                    'status_class': request_item.get('status_class', 'secondary'),
                    'current_stage': request_item.get('current_stage', 'Unknown')
                }
            
            # Get role context
            role_context = self.get_role_context()
            
            # Get statistics
            statistics = self.get_request_statistics()
            
            context = {
                'requests': requests_data,
                'current_page': page,
                'has_previous': page > 1,
                'has_next': has_next,
                'previous_page_number': page - 1 if page > 1 else None,
                'next_page_number': page + 1 if has_next else None,
                'search_query': search,
                'role_filter': role_filter,
                'status_filter': status_filter,
                'statistics': statistics,
                'role_context': role_context,
            }
            
            template_name = f"{role_context['template_base']}requests_list.html"
            return render(request, template_name, context)
            
        except Exception as e:
            messages.error(request, f"Error loading requests: {str(e)}")
            role_context = self.get_role_context()
            template_name = f"{role_context['template_base']}requests_list.html"
            return render(request, template_name, {
                'requests': [],
                'error': str(e),
                'role_context': role_context,
            })


class StaffRequestDetailView(StaffRequestMixin, View):
    """Unified staff request detail view for all roles."""
    
    def __init__(self, role: str):
        self.role = role
        super().__init__()

    @method_decorator(login_required)
    def get(self, request, staff_acc_req_id):
        """Handle GET request for staff request detail."""
        try:
            # Get request detail using SQL function
            request_data = self.execute_sql_function('get_staff_request_detail', [staff_acc_req_id])
            
            if not request_data:
                messages.error(request, "Staff request not found.")
                role_context = self.get_role_context()
                return redirect(role_context['list_url'])
            
            request_detail = request_data[0]
            
            # Add progress information
            request_detail['progress'] = {
                'progress_percent': request_detail.get('progress_percent', 0),
                'status_class': request_detail.get('status_class', 'secondary'),
                'current_stage': request_detail.get('current_stage', 'Unknown')
            }
            
            # Parse status history if it exists
            status_history = request_detail.get('status_history', '[]')
            if isinstance(status_history, str):
                try:
                    status_history = json.loads(status_history)
                except json.JSONDecodeError:
                    status_history = []
            
            request_detail['status_history_parsed'] = status_history
            
            # Get role context
            role_context = self.get_role_context()
            
            context = {
                'request': request_detail,
                'role_context': role_context,
            }
            
            template_name = f"{role_context['template_base']}request_detail.html"
            return render(request, template_name, context)
            
        except Exception as e:
            messages.error(request, f"Error loading request details: {str(e)}")
            role_context = self.get_role_context()
            return redirect(role_context['list_url'])

    @method_decorator(login_required)
    def post(self, request, staff_acc_req_id):
        """Handle POST request for status updates (for authorized roles)."""
        if self.role not in ['secretary', 'captain']:
            messages.error(request, "You don't have permission to update request status.")
            role_context = self.get_role_context()
            return redirect(role_context['detail_url'], staff_acc_req_id=staff_acc_req_id)
        
        try:
            new_status_id = request.POST.get('status_id')
            remarks = request.POST.get('remarks', '').strip()
            
            if not new_status_id:
                messages.error(request, "Status is required.")
                role_context = self.get_role_context()
                return redirect(role_context['detail_url'], staff_acc_req_id=staff_acc_req_id)
            
            # Get current user's staff ID (implement based on your auth system)
            staff_id = getattr(request.user, 'staff_id', None)
            if not staff_id:
                messages.error(request, "Unable to identify staff member.")
                role_context = self.get_role_context()
                return redirect(role_context['detail_url'], staff_acc_req_id=staff_acc_req_id)
            
            # Update status using SQL function
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT update_staff_request_status(%s, %s, %s, %s)",
                    [staff_acc_req_id, int(new_status_id), staff_id, remarks]
                )
                success = cursor.fetchone()[0]
            
            if success:
                messages.success(request, "Request status updated successfully.")
            else:
                messages.error(request, "Failed to update request status.")
            
            role_context = self.get_role_context()
            return redirect(role_context['detail_url'], staff_acc_req_id=staff_acc_req_id)
            
        except Exception as e:
            messages.error(request, f"Error updating request: {str(e)}")
            role_context = self.get_role_context()
            return redirect(role_context['detail_url'], staff_acc_req_id=staff_acc_req_id)


@require_http_methods(["GET"])
@login_required
def staff_request_api(request, role: str):
    """API endpoint for staff request data (for AJAX calls)."""
    try:
        search = request.GET.get('search', '').strip()
        role_filter = request.GET.get('role_filter', '')
        status_filter = request.GET.get('status_filter', '')
        
        # Convert status filter
        try:
            status_filter_int = int(status_filter) if status_filter else None
        except (ValueError, TypeError):
            status_filter_int = None
        
        # Get requests using SQL function
        params = [
            role_filter if role_filter else None,
            status_filter_int,
            50,  # Limit for API
            0,   # No offset for API
            search if search else None
        ]
        
        mixin = StaffRequestMixin()
        mixin.role = role
        requests_data = mixin.execute_sql_function('get_staff_requests_list', params)
        
        # Add progress information
        for request_item in requests_data:
            request_item['progress'] = {
                'progress_percent': request_item.get('progress_percent', 0),
                'status_class': request_item.get('status_class', 'secondary'),
                'current_stage': request_item.get('current_stage', 'Unknown')
            }
        
        return JsonResponse({
            'success': True,
            'requests': requests_data,
            'count': len(requests_data)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# Factory functions to create role-specific views
def create_staff_request_list_view(role: str):
    """Factory function to create role-specific list view."""
    class RoleSpecificListView(StaffRequestListView):
        def __init__(self):
            self.role = role
            super().__init__(role)
    return RoleSpecificListView.as_view()

def create_staff_request_detail_view(role: str):
    """Factory function to create role-specific detail view."""
    class RoleSpecificDetailView(StaffRequestDetailView):
        def __init__(self):
            self.role = role
            super().__init__(role)
    return RoleSpecificDetailView.as_view()


# Role-specific view instances
secretary_request_list = create_staff_request_list_view('secretary')
secretary_request_detail = create_staff_request_detail_view('secretary')

captain_request_list = create_staff_request_list_view('captain')
captain_request_detail = create_staff_request_detail_view('captain')

midwife_request_list = create_staff_request_list_view('midwife')
midwife_request_detail = create_staff_request_detail_view('midwife')

lupon_pres_request_list = create_staff_request_list_view('lupon_pres')
lupon_pres_request_detail = create_staff_request_detail_view('lupon_pres')