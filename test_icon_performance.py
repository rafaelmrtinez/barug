"""
Test script to measure bootstrap icon rendering performance
Run with: python test_icon_performance.py
"""
import time
import django
import os

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'barug.settings')
django.setup()

from django.template import Template, Context
from django.core.cache import cache

# Clear cache to start fresh
cache.clear()
print("Cache cleared\n")

# Test template with 100 icons (similar to case_detail.html)
template_original = """
{% load bootstrap_icons %}
{% for i in range %}
    {% bs_icon 'calendar' %}
    {% bs_icon 'file-earmark-text' %}
    {% bs_icon 'person' %}
    {% bs_icon 'check-circle' %}
    {% bs_icon 'clock' %}
{% endfor %}
"""

template_cached = """
{% load cached_icons %}
{% for i in range %}
    {% bs_icon_cached 'calendar' %}
    {% bs_icon_cached 'file-earmark-text' %}
    {% bs_icon_cached 'person' %}
    {% bs_icon_cached 'check-circle' %}
    {% bs_icon_cached 'clock' %}
{% endfor %}
"""

# Test with 20 iterations (100 icons total)
context = Context({'range': range(20)})

print("=" * 60)
print("BOOTSTRAP ICON PERFORMANCE TEST")
print("=" * 60)
print(f"Testing with 100 icon renders (20 iterations × 5 icons)\n")

# Test original (uncached)
print("1. Testing ORIGINAL bs_icon (uncached)...")
template_obj = Template(template_original)
start = time.time()
result = template_obj.render(context)
duration_original = time.time() - start
print(f"   Time: {duration_original:.3f} seconds")
print(f"   Output length: {len(result)} characters\n")

# Clear cache
cache.clear()

# Test cached - first run (cache miss)
print("2. Testing CACHED bs_icon_cached (first run - cache miss)...")
template_obj = Template(template_cached)
start = time.time()
result = template_obj.render(context)
duration_cached_first = time.time() - start
print(f"   Time: {duration_cached_first:.3f} seconds")
print(f"   Output length: {len(result)} characters\n")

# Test cached - second run (cache hit)
print("3. Testing CACHED bs_icon_cached (second run - cache hit)...")
start = time.time()
result = template_obj.render(context)
duration_cached_second = time.time() - start
print(f"   Time: {duration_cached_second:.3f} seconds")
print(f"   Output length: {len(result)} characters\n")

# Calculate improvements
improvement_first = ((duration_original - duration_cached_first) / duration_original) * 100
improvement_second = ((duration_original - duration_cached_second) / duration_original) * 100
speedup = duration_original / duration_cached_second

print("=" * 60)
print("RESULTS SUMMARY")
print("=" * 60)
print(f"Original (uncached):        {duration_original:.3f}s")
print(f"Cached (first run):         {duration_cached_first:.3f}s ({improvement_first:+.1f}%)")
print(f"Cached (subsequent runs):   {duration_cached_second:.3f}s ({improvement_second:+.1f}%)")
print(f"\nSpeedup: {speedup:.1f}x faster with caching!")
print("=" * 60)

# Extrapolate to case_detail.html (100+ icons)
print("\nEXTRAPOLATION TO CASE DETAIL PAGE:")
print(f"If case_detail.html has 100+ icon calls:")
print(f"  - Original rendering: ~{duration_original * 1:.1f}s")
print(f"  - Cached rendering:   ~{duration_cached_second * 1:.1f}s")
print(f"  - Time saved:         ~{(duration_original - duration_cached_second) * 1:.1f}s per page load")
print("=" * 60)
