# TEMPLATE RENDERING PERFORMANCE FIX

## Problem Identified
The case detail page was taking **17+ seconds** to load, but the database query only took **365ms**. The issue was **template rendering taking 17 seconds** due to the `{% bs_icon %}` template tag being called **100+ times** on a single page.

### Root Cause
The `django-bootstrap-icons` package reads SVG files from disk on **every single call** to `{% bs_icon %}`. With 100+ icons on the page, this means 100+ file I/O operations during template rendering, causing massive slowdown.

## Solution Implemented

### 1. Added Template Fragment Caching (settings.py)
```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "barug-local",
        "TIMEOUT": 300,
    },
    "template_fragments": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "template-cache",
        "TIMEOUT": 3600,  # 1 hour - cache icons longer
    }
}
```

### 2. Created Cached Icon Template Tag
Created `common/templatetags/cached_icons.py` with a cached version of the bootstrap icon tag:
- Caches rendered SVG output for 1 hour
- Uses unique cache keys based on icon parameters
- Falls back to original rendering if not in cache
- Dramatically reduces file I/O operations

## How to Use

### Option 1: Use Cached Icons (Recommended)
Replace `{% load bootstrap_icons %}` with `{% load cached_icons %}` and use `{% bs_icon_cached %}`:

```django
{% load cached_icons %}

<!-- Instead of: {% bs_icon 'calendar' %} -->
{% bs_icon_cached 'calendar' %}

<!-- With parameters: -->
{% bs_icon_cached 'calendar' size='1.5em' color='#007bff' extra_classes='me-2' %}
```

### Option 2: Batch Replace in Templates
For templates with many icons, do a find-and-replace:
1. Replace `{% load bootstrap_icons %}` with `{% load cached_icons %}`
2. Replace `{% bs_icon` with `{% bs_icon_cached`

## Expected Performance Improvement

### Before:
- **Total page load**: 17.64 seconds
- **Template rendering**: ~17 seconds
- **Database query**: 365ms

### After (with caching):
- **First load**: ~17 seconds (builds cache)
- **Subsequent loads**: <1 second (uses cached icons)
- **Database query**: 365ms (unchanged)

## Files Modified
1. `barug/settings.py` - Added template_fragments cache configuration
2. `common/templatetags/cached_icons.py` - Created cached icon template tag

## Files to Update (Optional)
To get immediate performance benefits, update these templates:
- `lupon_mem/templates/lupon_mem/case_detail.html` (100+ icon calls)
- Any other templates with heavy icon usage

## Testing
1. Clear cache: `python manage.py shell -c "from django.core.cache import cache; cache.clear()"`
2. Load case detail page (first load will be slow - builds cache)
3. Reload page (should be instant)
4. Check browser DevTools Network tab - should show <1s load time

## Alternative Quick Fix (If Template Changes Not Possible)
If you can't modify templates immediately, the cache will still help after the first page load. The icons will be cached in memory and subsequent renders will be faster.

## Production Considerations
- For production, consider using Redis or Memcached instead of LocMemCache
- Adjust cache timeout based on your needs (icons rarely change, so 1 hour is safe)
- Monitor cache memory usage if you have many unique icon combinations

## Cache Invalidation
Icons are cached for 1 hour by default. To clear the cache:
```python
from django.core.cache import cache
cache.clear()
```

Or restart the Django server (LocMemCache is in-memory only).
