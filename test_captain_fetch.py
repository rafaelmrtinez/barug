"""Test fetching barangay captain name from database"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'barug.settings')
django.setup()

from clerk.services.pdf_service import _get_barangay_captain_name

print("Testing barangay captain name fetch...")
print("-" * 50)

captain_name = _get_barangay_captain_name()

print(f"Captain Name: {captain_name}")
print("-" * 50)

if captain_name and captain_name != "Lourdes R. Ramirez":
    print("[OK] Successfully fetched captain name from database")
else:
    print("[INFO] Using fallback captain name")
