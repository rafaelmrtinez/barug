import requests

SUPABASE_URL = "https://ucvhvzimwtkrilyyhffc.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVjdmh2emltd3RrcmlseXloZmZjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTA2NjkwNzksImV4cCI6MjA2NjI0NTA3OX0.gABmHzJYb-HeYpJTcZdWFQhzJ7zkrzQu4eWZP5fR4_4"
EDGE_FUNCTION_NAME = "upload-api"

file_path = "./test_data.xlsx"

with open(file_path, "rb") as file:
    files = {
        "file": (
            "test_data.xlsx",  # just the filename, not full path
            file,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    }

    data = {
        "uploaded_by": "juan.dela.cruz@barangay.gov.ph"  # or however you track users
    }

    print(f"Uploading {file_path} to Supabase Edge Function...")

    response = requests.post(
        f"{SUPABASE_URL}/functions/v1/{EDGE_FUNCTION_NAME}",
        headers={
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        },
        files=files,
        data=data  # this is the form field that the edge function expects
    )

print(response.status_code)
print(response.text)
