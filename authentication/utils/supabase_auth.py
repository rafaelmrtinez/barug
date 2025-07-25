# utils/supabase_auth.py

import requests
from django.conf import settings

def delete_supabase_user(user_id):
    # [DEBUG] print(f"🧹 Attempting to delete Supabase user: {user_id}")
    url = f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}"
    }

    try:
        response = requests.delete(url, headers=headers)
        # [DEBUG] print(f"🔧 DELETE status: {response.status_code}")
        # [DEBUG] print(f"📦 DELETE response: {response.text}")
        return response.status_code
    except Exception as e:
        print(f"🔥 Error deleting user from Supabase: {str(e)}")
        return 500
