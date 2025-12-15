# Skill Test Preparation Guide

## Common Tasks You Might Be Asked

### 1. Add Print Feature to a Page

#### Step 1: Add Print Button to Template
```html
<!-- Add this button in your toolbar or header -->
<button onclick="window.print()" class="btn btn-hero">
    {% bs_icon 'printer' extra_classes='me-2' %} Print
</button>
```

#### Step 2: Add Print Styles to Template
```html
{% block css %}
<style>
    /* Hide elements when printing */
    @media print {
        .no-print, .toolbar, .hero-right, .btn, .actions, .searchbox {
            display: none !important;
        }
        
        .hero {
            position: static;
            background: white !important;
            border: none !important;
            color: black !important;
        }
        
        .table {
            font-size: 10pt;
        }
        
        /* Show all rows when printing */
        .table tbody tr {
            page-break-inside: avoid;
        }
        
        /* Add page header */
        @page {
            margin: 1cm;
        }
        
        body {
            background: white;
        }
    }
</style>
{% endblock %}
```

---

### 2. Add Export to PDF Feature

#### Step 1: Install Required Package
```bash
pip install reportlab
```

#### Step 2: Create PDF View
```python
from django.http import HttpResponse
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

@session_login_required
@role_required(*LUPON_ROLES)
def export_residents_pdf(request):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="resident_records.pdf"'
    
    doc = SimpleDocTemplate(response, pagesize=A4)
    elements = []
    
    # Get data
    with connection.cursor() as cur:
        cur.execute("SELECT person_id, first_name, last_name FROM person LIMIT 50")
        residents = cur.fetchall()
    
    # Create table
    data = [['ID', 'First Name', 'Last Name']]
    for r in residents:
        data.append([str(r[0]), r[1], r[2]])
    
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    doc.build(elements)
    return response
```

#### Step 3: Add URL
```python
# urls.py
path('residents/export-pdf/', views.export_residents_pdf, name='export_residents_pdf'),
```

#### Step 4: Add Button
```html
<a href="{% url 'lupon_mem:export_residents_pdf' %}" class="btn btn-hero">
    {% bs_icon 'file-pdf' extra_classes='me-2' %} Export PDF
</a>
```

---

### 3. Add Export to Excel Feature

#### Step 1: Install Package
```bash
pip install openpyxl
```

#### Step 2: Create Excel View
```python
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

@session_login_required
@role_required(*LUPON_ROLES)
def export_residents_excel(request):
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="resident_records.xlsx"'
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Resident Records"
    
    # Headers
    headers = ['ID', 'Full Name', 'Complainant Reports', 'Respondent Reports']
    ws.append(headers)
    
    # Style headers
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    
    # Get data
    with connection.cursor() as cur:
        cur.execute("""
            SELECT person_id, 
                   CONCAT(first_name, ' ', last_name) as full_name,
                   (SELECT COUNT(*) FROM complainant_report WHERE person_id = p.person_id),
                   (SELECT COUNT(*) FROM respondent_report WHERE person_id = p.person_id)
            FROM person p
            LIMIT 100
        """)
        for row in cur.fetchall():
            ws.append(row)
    
    wb.save(response)
    return response
```

---

### 4. Add Search/Filter Feature

#### Step 1: Update View
```python
def resident_records_list(request):
    search_query = request.GET.get('q', '').strip()
    filter_type = request.GET.get('type', 'all')  # all, complainant, respondent
    
    where_clause = "WHERE 1=1"
    params = []
    
    if search_query:
        where_clause += " AND (first_name ILIKE %s OR last_name ILIKE %s)"
        params.extend([f'%{search_query}%', f'%{search_query}%'])
    
    if filter_type == 'complainant':
        where_clause += " AND EXISTS(SELECT 1 FROM complainant_report WHERE person_id = p.person_id)"
    elif filter_type == 'respondent':
        where_clause += " AND EXISTS(SELECT 1 FROM respondent_report WHERE person_id = p.person_id)"
    
    with connection.cursor() as cur:
        cur.execute(f"SELECT * FROM person p {where_clause}", params)
        residents = cur.fetchall()
    
    return render(request, 'template.html', {'residents': residents})
```

#### Step 2: Add Filter Form
```html
<form method="get">
    <input type="text" name="q" placeholder="Search..." value="{{ search_query }}">
    <select name="type">
        <option value="all">All</option>
        <option value="complainant" {% if filter_type == 'complainant' %}selected{% endif %}>Complainant</option>
        <option value="respondent" {% if filter_type == 'respondent' %}selected{% endif %}>Respondent</option>
    </select>
    <button type="submit">Search</button>
</form>
```

---

### 5. Add Pagination

```python
from django.core.paginator import Paginator

def my_view(request):
    items = MyModel.objects.all()
    paginator = Paginator(items, 20)  # 20 items per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'template.html', {'page_obj': page_obj})
```

```html
<!-- Template -->
{% for item in page_obj %}
    <!-- Display item -->
{% endfor %}

<!-- Pagination controls -->
<div class="pagination">
    {% if page_obj.has_previous %}
        <a href="?page=1">First</a>
        <a href="?page={{ page_obj.previous_page_number }}">Previous</a>
    {% endif %}
    
    <span>Page {{ page_obj.number }} of {{ page_obj.paginator.num_pages }}</span>
    
    {% if page_obj.has_next %}
        <a href="?page={{ page_obj.next_page_number }}">Next</a>
        <a href="?page={{ page_obj.paginator.num_pages }}">Last</a>
    {% endif %}
</div>
```

---

### 6. Add AJAX Feature (Load Data Without Page Refresh)

#### Step 1: Create API View
```python
from django.http import JsonResponse

def get_residents_api(request):
    search = request.GET.get('q', '')
    with connection.cursor() as cur:
        cur.execute("SELECT person_id, first_name, last_name FROM person WHERE first_name ILIKE %s", [f'%{search}%'])
        residents = [{'id': r[0], 'first_name': r[1], 'last_name': r[2]} for r in cur.fetchall()]
    return JsonResponse({'residents': residents})
```

#### Step 2: Add JavaScript
```html
<script>
function searchResidents() {
    const query = document.getElementById('searchInput').value;
    
    fetch(`/api/residents/?q=${query}`)
        .then(response => response.json())
        .then(data => {
            const container = document.getElementById('resultsContainer');
            container.innerHTML = '';
            
            data.residents.forEach(resident => {
                container.innerHTML += `
                    <div class="resident-card">
                        <h5>${resident.first_name} ${resident.last_name}</h5>
                    </div>
                `;
            });
        });
}
</script>

<input type="text" id="searchInput" onkeyup="searchResidents()">
<div id="resultsContainer"></div>
```

---

### 7. Add Form Validation

```python
from django import forms

class ResidentForm(forms.Form):
    first_name = forms.CharField(max_length=100, required=True)
    last_name = forms.CharField(max_length=100, required=True)
    email = forms.EmailField(required=False)
    age = forms.IntegerField(min_value=0, max_value=150)
    
    def clean_first_name(self):
        name = self.cleaned_data['first_name']
        if not name.isalpha():
            raise forms.ValidationError("Name must contain only letters")
        return name.title()
```

---

### 8. Add Modal/Popup

```html
<!-- Button trigger -->
<button type="button" data-bs-toggle="modal" data-bs-target="#myModal">
    Open Modal
</button>

<!-- Modal -->
<div class="modal fade" id="myModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Modal Title</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                <p>Modal content here</p>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                <button type="button" class="btn btn-primary">Save</button>
            </div>
        </div>
    </div>
</div>
```

---

## Quick Checklist for Skill Test

- [ ] Know how to add a new view function
- [ ] Know how to create a URL pattern
- [ ] Know how to create/modify templates
- [ ] Know how to query database (raw SQL or ORM)
- [ ] Know how to add forms
- [ ] Know how to add validation
- [ ] Know how to add print/export features
- [ ] Know how to add search/filter
- [ ] Know how to add pagination
- [ ] Know how to use Bootstrap components
- [ ] Know how to add JavaScript functionality
- [ ] Know how to handle POST requests
- [ ] Know how to use sessions
- [ ] Know how to add authentication/authorization

---

## Common Django Patterns

### URL Pattern
```python
# urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('residents/', views.resident_list, name='resident_list'),
    path('residents/<int:id>/', views.resident_detail, name='resident_detail'),
]
```

### View Function
```python
def my_view(request):
    if request.method == 'POST':
        # Handle form submission
        form = MyForm(request.POST)
        if form.is_valid():
            # Process data
            return redirect('success_page')
    else:
        form = MyForm()
    
    return render(request, 'template.html', {'form': form})
```

### Template Inheritance
```html
<!-- base.html -->
<!DOCTYPE html>
<html>
<head>
    {% block css %}{% endblock %}
</head>
<body>
    {% block content %}{% endblock %}
    {% block js %}{% endblock %}
</body>
</html>

<!-- child.html -->
{% extends 'base.html' %}
{% block content %}
    <h1>My Content</h1>
{% endblock %}
```

Good luck with your skill test! 🎯
