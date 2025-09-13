from django.utils import timezone

def auth_context(request):
    auth = request.session.get("auth") or {}
    role_name = auth.get("role_name", "")

    # Build the fullname from parts
    first_name = auth.get("first_name", "")
    last_name = auth.get("last_name", "")
    middle_name = auth.get("middle_name", "")
    suffix = auth.get("suffix", "")

    # Format full name: Lastname, Firstname Middlename Suffix
    user_fullname = " ".join(
        part for part in [last_name, first_name, middle_name, suffix] if part
    )

    return {
        "staff_id": auth.get("staff_id", 0),
        "user_fullname": user_fullname.strip(),
        "user_role": role_name,
        "user_role_template": role_name.lower().replace(" ", "_") if role_name else "",
    }
