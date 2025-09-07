# scripts/test_sms.py
import os, sys, pathlib

# Ensure the project root (where manage.py lives) is on sys.path
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "barug.settings")
import django
django.setup()

from notifications.services import send_doc_status_sms

def run():
    phone  = "19708072822"   # change to your phone
    ref_no = "DOC-12345"

    ok, info = send_doc_status_sms(phone, ref_no, "APPROVED")
    print("Approved SMS:", ok, info)

    ok, info = send_doc_status_sms(phone, ref_no, "REJECTED", reason="Incomplete requirements")
    print("Rejected SMS:", ok, info)

if __name__ == "__main__":
    run()
