# Walk-in Resident Search Functions

## Overview
This document details the specific functions used for the resident search functionality in the walk-in request page (`http://127.0.0.1:8000/clerk/walkin/`).

---

## Frontend (JavaScript)

### Search Input
**File:** `clerk/templates/clerk/walkin_request.html`  
**Element:** `<input id="residentSearch">` (Line ~125)

**Placeholder:** "Search by code or name (min 2 chars)"

### JavaScript Function
**Function:** `doSearch(q)` (async function)

**Trigger:** Input event with 250ms debounce

**Code:**
```javascript
async function doSearch(q) {
  if (!q || q.trim().length < 2) {
    wrap.innerHTML = '<div class="help">Type at least 2 characters…</div>';
    hideSpinner(); return;
  }
  showSpinner();
  try{
    const resp = await fetch(`${URL_SEARCH}?q=${encodeURIComponent(q)}`, { 
      headers: { "X-Requested-With":"fetch" } 
    });
    const html = await resp.text();
    wrap.innerHTML = html || '<div class="help">No results.</div>';
  }catch{
    wrap.innerHTML = '<div class="text-danger small">Search failed. Please try again.</div>';
  }finally{
    hideSpinner();
  }
}
```

**Endpoint Variable:**
```javascript
const URL_SEARCH = "{% url 'clerk:ajax_resident_search' %}";
// Resolves to: /clerk/ajax/resident-search/
```

---

## Backend (Django)

### URL Route
**File:** `clerk/urls.py` (Line 32)

```python
path("ajax/resident-search/", views.ajax_resident_search, name="ajax_resident_search"),
```

**Full URL:** `/clerk/ajax/resident-search/`

### Django View Function
**File:** `clerk/views.py` (Line 1384)  
**Function:** `ajax_resident_search(request: HttpRequest)`

**Code:**
```python
def ajax_resident_search(request: HttpRequest):
    """Debounced live search via RPC; returns an HTML fragment."""
    q = (request.GET.get("q") or "").strip()
    rows: List[Dict[str, Any]] = []

    if len(q) >= 2:
        try:
            res = supabase.rpc("search_person_by_code_or_name", {"p_key": q}).execute()
            rows = res.data or []
        except Exception as e:
            logger.warning("ajax_resident_search RPC failed: %s", e)
            rows = []

    html = render_to_string("clerk/doc_req/_resident_results.html", {"residents": rows})
    return HttpResponse(html)
```

**Parameters:**
- `q` - Search query from GET parameter (minimum 2 characters)

**Returns:** HTML fragment rendered from template

---

## Supabase RPC Function

### Function Name
**`search_person_by_code_or_name_not_deceased`**

### Parameters
```json
{
  "p_key": "search_query_string"
}
```

### What it does:
- Searches the `person` table by:
  - **Person code** (e.g., resident ID/code)
  - **Person name** (first name, middle name, last name)
- Returns matching person records
- Likely uses PostgreSQL's `ILIKE` or full-text search for fuzzy matching

### Return Format
Returns an array of person objects, likely containing:
- `person_id`
- `person_code`
- `first_name`
- `middle_name`
- `last_name`
- `suffix`
- Other person details

---

## Template for Results

### Template File
**File:** `clerk/templates/clerk/doc_req/_resident_results.html`

**Purpose:** Renders the search results as clickable HTML elements

**Expected Structure:**
```html
<!-- Each result has a button with data attributes -->
<button class="pick-resident" 
        data-person-id="{{ resident.person_id }}"
        data-display="{{ resident.full_name }}">
  <!-- Display resident info -->
</button>
```

---

## On-Behalf Search

The same search functionality is also used for the "on-behalf" person search:

### JavaScript Function
**Function:** `doOnBehalfSearch(q)` (async function)

**Uses the same:**
- Endpoint: `ajax_resident_search`
- RPC function: `search_person_by_code_or_name`
- Template: `_resident_results.html`

---

## Flow Summary

1. **User types** in search box (min 2 characters)
2. **JavaScript** debounces input (250ms delay)
3. **AJAX request** sent to `/clerk/ajax/resident-search/?q=<query>`
4. **Django view** (`ajax_resident_search`) receives request
5. **Supabase RPC** called: `search_person_by_code_or_name_not_deceased(p_key: query)`
6. **Database** searches person table by code or name
7. **Results** returned to Django view
8. **Template** renders results as HTML fragment
9. **JavaScript** displays results in the page
10. **User clicks** a result to select the resident

---

## Key Points

- **Minimum characters:** 2 (enforced in both frontend and backend)
- **Debounce delay:** 250ms (prevents excessive API calls)
- **Search method:** Fuzzy search by person code OR name
- **Response type:** HTML fragment (not JSON)
- **Supabase function:** `search_person_by_code_or_name_not_deceased`
- **Single RPC call:** Used for both main resident search and on-behalf search

---

## Database Function Location

The actual PostgreSQL function `search_person_by_code_or_name_not_deceased` is defined in your Supabase database, likely in the `public` schema or a custom schema. To view its implementation, you would need to check:

1. Supabase Dashboard → SQL Editor
2. Or query: `SELECT prosrc FROM pg_proc WHERE proname = 'search_person_by_code_or_name_not_deceased';`

The function filters out deceased persons (person_status_id <> 3) and only returns residents (residential_status_id = 2). It searches by person code or name patterns and returns person details with address information.
