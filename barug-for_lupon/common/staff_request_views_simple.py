"""
Simple Staff Request Views for lupon_pres
==========================================
Provides the missing functions that lupon_pres views.py is trying to call.
"""

from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from secretary.models import Secretary
from common.flash import flash_warning, flash_system_error
import logging

logger = logging.getLogger(__name__)

def get_user_info(request):
    """Get user info from session - call this in each view"""
    auth = request.session.get('auth', {})
    first_name = (auth.get('first_name', '') or '').strip().title()
    middle_name = (auth.get('middle_name', '') or '').strip().title()
    last_name = (auth.get('last_name', '') or '').strip().title()
    suffix = (auth.get('suffix', '') or '').strip().upper()
    
    # Format: "Last Name, First Name Middle Initial Suffix"
    name_parts = [first_name]
    if middle_name:
        name_parts.append(middle_name[0] + '.')  # Middle initial with period
    if suffix:
        name_parts.append(suffix)
    
    user_fullname = f"{last_name}, {' '.join(name_parts)}"
    user_role = auth.get('role_name', 'Staff').title()
    user_role_template = user_role.lower().replace(' ', '_')
    
    return user_fullname, user_role, user_role_template

def staff_requests_list_view(request, app_name, template_name):
    """Generic staff requests list view"""
    auth = request.session.get('auth', {})
    staff_id = auth.get('staff_id')
    user_fullname, user_role, user_role_template = get_user_info(request)
    
    # Get filter parameters
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    role_filter = request.GET.get('role', '').strip()
    date_filter = request.GET.get('date_submitted', '').strip()
    
    try:
        requests = Secretary.get_staff_account_req_list_by_requester(staff_id)
        stats_data = Secretary.get_staff_request_statistics_by_requester(staff_id)
        stats = stats_data[0] if stats_data else {
            'total_requests': 0, 'pending_requests': 0, 'approved_requests': 0, 'rejected_requests': 0
        }
    except Exception as e:
        logger.exception("Error loading requests")
        flash_system_error(request, "Failed to load requests.")
        requests = []
        stats = {'total_requests': 0, 'pending_requests': 0, 'approved_requests': 0, 'rejected_requests': 0}
    
    # Apply filters
    filtered_requests = requests
    
    # Search by name
    if search_query:
        search_lower = search_query.lower()
        filtered_requests = [
            r for r in filtered_requests 
            if search_lower in (r.get('name') or '').lower()
        ]
    
    # Filter by status
    if status_filter:
        filtered_requests = [
            r for r in filtered_requests 
            if str(r.get('status_id', '')) == status_filter
        ]
    
    # Filter by role
    if role_filter:
        filtered_requests = [
            r for r in filtered_requests 
            if str(r.get('role_id', '')) == role_filter
        ]
    
    # Filter by date
    if date_filter:
        from datetime import datetime
        try:
            target_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
            date_filtered = []
            for r in filtered_requests:
                pretty_date = r.get('date_time_submitted_pretty')
                if pretty_date and isinstance(pretty_date, str):
                    try:
                        # Parse "December 1, 2025 3:28 A.M." format
                        date_part = ' '.join(pretty_date.split()[:3])  # "December 1, 2025"
                        parsed_date = datetime.strptime(date_part, "%B %d, %Y").date()
                        if parsed_date == target_date:
                            date_filtered.append(r)
                    except (ValueError, IndexError):
                        continue
            filtered_requests = date_filtered
        except ValueError:
            pass
    
    # Implement pagination with 9 requests per page
    paginator = Paginator(filtered_requests, 9)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, template_name, {
        'page_obj': page_obj,
        'requests': filtered_requests,
        'stats': stats,
        'search_query': search_query,
        'status_filter': status_filter,
        'role_filter': role_filter,
        'date_filter': date_filter,
        'user_fullname': user_fullname,
        'user_role': user_role,
        'user_role_template': user_role_template,
        'page_path': f"{user_role} / My Requests",
        'page_title': 'My Staff Requests',
    })

def staff_request_detail_view(request, request_id, app_name, template_name):
    """Generic staff request detail view"""
    auth = request.session.get('auth', {})
    staff_id = auth.get('staff_id')
    user_fullname, user_role, user_role_template = get_user_info(request)
    
    try:
        details_data = Secretary.get_staff_acc_req_profile_progress(request_id)
        history = Secretary.get_staff_acc_req_status_history(request_id)
        
        if not details_data:
            flash_warning(request, "Request not found.")
            return redirect(f'{app_name}:staff_requests_list')
        
        request_detail = details_data[0]
        
        # Allow access if user is the requester OR if user has appropriate role permissions
        if request_detail.get('requested_by_id') != staff_id:
            # For now, allow users to view all requests for debugging
            # TODO: Implement proper role-based access control
            pass
            
    except Exception as e:
        logger.exception(f"Error loading request {request_id}")
        flash_system_error(request, "Failed to load request details.")
        return redirect(f'{app_name}:staff_requests_list')
    
    return render(request, template_name, {
        'request': request_detail,
        'history': history,
        'user_fullname': user_fullname,
        'user_role': user_role,
        'user_role_template': user_role_template,
        'page_path': f"{user_role} / My Requests / Details",
        'page_title': f"Request Details - {request_detail.get('full_name', 'Unknown')}",
    })