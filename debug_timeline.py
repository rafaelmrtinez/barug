import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'barug.settings')
django.setup()

from lupon_mem.services.timeline import get_case_timeline

result = get_case_timeline(22)
print(f"Total events: {len(result['events'])}")
print("\nFirst 10 events:")
for i, ev in enumerate(result['events'][:10]):
    print(f"{i+1}. {ev['dt']} | ts={ev['ts']:.2f} | {ev['kind']} | {ev['title']}")
