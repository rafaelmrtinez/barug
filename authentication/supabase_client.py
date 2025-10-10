from supabase import create_client
from django.conf import settings

# ✅ MUST be the SERVICE ROLE key for server-side uploads
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
