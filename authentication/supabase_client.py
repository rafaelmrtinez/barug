# authentication/supabase_client.py
import os
from supabase import create_client

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # server-side
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_ID_UPLOADS_BUCKET = os.getenv("SUPABASE_ID_UPLOADS_BUCKET", "id-uploads")
assert SUPABASE_URL, "SUPABASE_URL not set"
assert SUPABASE_SERVICE_ROLE_KEY, "SUPABASE_SERVICE_ROLE_KEY not set"

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
