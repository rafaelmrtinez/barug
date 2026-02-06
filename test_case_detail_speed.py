import time
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'barug.settings')
django.setup()

from django.test import RequestFactory
from lupon_mem.views_cases import case_detail

# Create fake request
factory = RequestFactory()
request = factory.get('/lupon_mem/cases/2/')
request.session = {
    'auth': {
        'role_name': 'BARANGAY LUPON MEMBER',
        'staff_id': 1
    }
}

print("Testing case_detail view performance...")
print("=" * 60)

t0 = time.perf_counter()
try:
    response = case_detail(request, case_id=2)
    t1 = (time.perf_counter() - t0) * 1000
    print(f"✓ Server response time: {t1:.0f}ms")
    print(f"✓ Status code: {response.status_code}")
    
    if t1 > 2000:
        print(f"\n⚠ WARNING: Server is taking {t1/1000:.1f}s!")
        print("The problem is in the Python code, not the frontend.")
    else:
        print(f"\n✓ Server is fast ({t1/1000:.1f}s)")
        print("The 20-second delay is likely in the TEMPLATE JAVASCRIPT.")
        print("\nCheck browser DevTools Network tab:")
        print("- Is the HTML response fast (<2s)?")
        print("- Are there slow API calls after page load?")
        print("- Check for: checkHearingStatus(), getMediationHearingDetails()")
        
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()

print("=" * 60)
