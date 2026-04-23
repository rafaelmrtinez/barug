from django.utils import timezone

# Context processor with multi-role support

def auth_context(request):
    auth = request.session.get("auth") or {}
    
    # Get primary role for display (backward compatibility)
    role_name = auth.get("role_name", "")
    
    # Get all roles for multi-role support
    role_names_list = auth.get("role_names_list", [])
    role_original = auth.get("role_original", "")
    
    staff_id = auth.get("staff_id")

    # Build the fullname from parts
    first_name = auth.get("first_name", "")
    last_name = auth.get("last_name", "")
    middle_name = auth.get("middle_name", "")
    suffix = auth.get("suffix", "")

    # Format full name: Lastname, Firstname Middlename Suffix
    user_fullname = " ".join(
        part for part in [last_name, first_name, middle_name, suffix] if part
    )

    # Get logged-in user's profile data for header (not viewed staff's profile)
    header_profile = {}
    if staff_id:
        from .models import Authentication
        try:
            header_profile = Authentication.get_staff_profile_by_id(staff_id) or {}
        except Exception:
            header_profile = {}

    # Get currently selected role for header display
    # For single role users, selected_role might not be set, so use role_name as fallback
    selected_role = auth.get("selected_role") or role_name
    
    return {
        "staff_id": staff_id or 0,
        "user_fullname": user_fullname.strip(),
        "user_role": selected_role,  # Current active role for header display
        "user_roles": role_names_list,  # All roles list
        "user_roles_display": role_original,  # Comma-separated roles from DB
        "selected_role": selected_role,  # Currently selected role
        "user_role_template": role_name.lower().replace(" ", "_") if role_name else "",
        "header_profile": header_profile,
        "lupon_sched": auth.get("lupon_sched", []),
    }
