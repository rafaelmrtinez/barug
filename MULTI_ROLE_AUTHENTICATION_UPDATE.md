# Multi-Role Authentication Update

## Overview
Updated the authentication system to support staff members with multiple roles, matching the new database function `staff_login2` that returns comma-separated active roles.

## Changes Made

### 1. Authentication Views (`authentication/views.py`)

#### Login Function Updates:
- **Role Parsing**: Modified to handle comma-separated roles from `staff_login2` function
- **Session Storage**: Added support for storing multiple roles:
  - `role_names_list`: List of all user roles
  - `role_original`: Original comma-separated string from database
  - `role_name`/`role_lower`: Primary role (first in list) for backward compatibility

#### New Helper Functions:
- `get_user_roles_from_session(request)`: Returns set of all user roles
- `get_primary_role_from_session(request)`: Returns primary role
- `has_any_role(request, *role_names)`: Check if user has any specified roles
- `session_login_required`: Alias for `staff_login_required`
- `any_role_required`: Alias for `roles_required` for clarity

#### Updated Decorators:
- `roles_required`: Now checks if user has ANY of the required roles
- `_role_home`: Updated with role priority for users with multiple roles

### 2. Authentication Guards (`authentication/guards.py`)

#### Updated Functions:
- `role_required`: Modified to support multiple roles per user
- `_safe_home_url`: Added role priority handling and more role mappings

### 3. Context Processors (`authentication/context_processors.py`)

#### New Template Variables:
- `user_roles`: List of all user roles
- `user_roles_display`: Comma-separated roles from database
- `user_role`: Primary role (unchanged for backward compatibility)

## Database Function Integration

The system now integrates with the new `staff_login2` function that returns:
```sql
RETURNS TABLE(
    user_id             integer,
    person_id           integer,
    user_type           text,
    role_name           text,   -- now returns comma-separated active roles
    first_name          text,
    middle_name         text,
    last_name           text,
    account_status_name text,
    login_log_id        integer
)
```

## Role Priority System

For users with multiple roles, the system uses this priority order:
1. Super Admin
2. Barangay Captain
3. Admin
4. Barangay Clerk
5. Barangay Treasurer
6. Barangay Secretary
7. Midwife
8. Barangay Health Worker
9. Nurse
10. Lupon President
11. Lupon Member

## Backward Compatibility

- Existing code using single roles continues to work
- Primary role is stored as the first role in the list
- All existing decorators and functions maintain their API
- Templates receive the primary role in `user_role` variable

## Usage Examples

### Checking Multiple Roles in Views:
```python
from authentication.views import has_any_role, get_user_roles_from_session

# Check if user has any of these roles
if has_any_role(request, 'clerk', 'treasurer', 'secretary'):
    # User has at least one of these roles
    pass

# Get all user roles
user_roles = get_user_roles_from_session(request)
```

### Using Decorators:
```python
from authentication.views import roles_required, any_role_required

# User needs ANY of these roles
@roles_required('clerk', 'treasurer')
def my_view(request):
    pass

# Same as above, but more explicit
@any_role_required('clerk', 'treasurer')  
def my_view(request):
    pass
```

### In Templates:
```html
<!-- Primary role (backward compatible) -->
<p>Role: {{ user_role }}</p>

<!-- All roles -->
<p>Roles: {{ user_roles_display }}</p>

<!-- Check for specific roles -->
{% if 'clerk' in user_roles or 'treasurer' in user_roles %}
    <!-- User has clerk or treasurer role -->
{% endif %}
```

## Testing

Test the multi-role functionality by:
1. Assigning multiple active roles to a staff member in the database
2. Logging in with that staff account
3. Verifying that role-based access control works correctly
4. Checking that the primary role dashboard is displayed
5. Ensuring all role-specific features are accessible

## Notes

- The system maintains full backward compatibility
- Primary role determines the default dashboard
- All role checks now support multiple roles
- Session data includes both individual roles and the original comma-separated string
- Role priority ensures consistent behavior for users with multiple roles