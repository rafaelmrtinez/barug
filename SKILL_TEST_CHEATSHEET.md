# 🎯 Skill Test Quick Cheat Sheet

## 1. Print Feature (FASTEST)
```html
<!-- Add button -->
<button onclick="window.print()" class="btn btn-primary">
    Print
</button>

<!-- Add print CSS -->
<style>
@media print {
    .no-print, .btn, .toolbar { display: none !important; }
    body { background: white; }
    .table { font-size: 10pt; }
}
</style>
```

## 2. Search Feature
```python
# View
def my_view(request):
    search = request.GET.get('q', '')
    if search:
        items = MyModel.objects.filter(name__icontains=search)
    else:
        items = MyModel.objects.all()
    return render(request, 'template.html', {'items': items})
```

```html
<!-- Template -->
<form method="get">
    <input type="text" name="q" value="{{ request.GET.q }}">
    <button type="submit">Search</button>
</form>
```

## 3. Add New Page (Complete Flow)

### Step 1: Create View (views.py)
```python
from django.shortcuts import render

def my_new_page(request):
    data = MyModel.objects.all()
    return render(request, 'app/my_page.html', {'data': data})
```

### Step 2: Add URL (urls.py)
```python
from django.urls import path
from . import views

urlpatterns = [
    path('my-page/', views.my_new_page, name='my_page'),
]
```

### Step 3: Create Template (templates/app/my_page.html)
```html
{% extends 'base.html' %}
{% block content %}
    <h1>My Page</h1>
    {% for item in data %}
        <p>{{ item.name }}</p>
    {% endfor %}
{% endblock %}
```

## 4. Form with Validation
```python
# forms.py
from django import forms

class MyForm(forms.Form):
    name = forms.CharField(max_length=100, required=True)
    email = forms.EmailField()
    age = forms.IntegerField(min_value=0)

# views.py
def my_form_view(request):
    if request.method == 'POST':
        form = MyForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name']
            # Save to database
            return redirect('success')
    else:
        form = MyForm()
    return render(request, 'form.html', {'form': form})
```

```html
<!-- Template -->
<form method="post">
    {% csrf_token %}
    {{ form.as_p }}
    <button type="submit">Submit</button>
</form>
```

## 5. Database Query (Raw SQL)
```python
from django.db import connection

def my_view(request):
    with connection.cursor() as cur:
        cur.execute("SELECT id, name FROM person WHERE age > %s", [18])
        results = cur.fetchall()
    return render(request, 'template.html', {'results': results})
```

## 6. Database Query (ORM)
```python
# Get all
items = MyModel.objects.all()

# Filter
items = MyModel.objects.filter(name='John')

# Get one
item = MyModel.objects.get(id=1)

# Count
count = MyModel.objects.count()

# Order
items = MyModel.objects.order_by('-created_at')

# Search (case-insensitive)
items = MyModel.objects.filter(name__icontains='john')
```

## 7. Pagination
```python
from django.core.paginator import Paginator

def my_view(request):
    items = MyModel.objects.all()
    paginator = Paginator(items, 20)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    return render(request, 'template.html', {'page_obj': page_obj})
```

```html
<!-- Template -->
{% for item in page_obj %}
    {{ item.name }}
{% endfor %}

<!-- Pagination -->
{% if page_obj.has_previous %}
    <a href="?page={{ page_obj.previous_page_number }}">Previous</a>
{% endif %}
<span>Page {{ page_obj.number }} of {{ page_obj.paginator.num_pages }}</span>
{% if page_obj.has_next %}
    <a href="?page={{ page_obj.next_page_number }}">Next</a>
{% endif %}
```

## 8. Export to Excel
```python
from django.http import HttpResponse
from openpyxl import Workbook

def export_excel(request):
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="data.xlsx"'
    
    wb = Workbook()
    ws = wb.active
    ws.append(['ID', 'Name', 'Email'])
    
    for item in MyModel.objects.all():
        ws.append([item.id, item.name, item.email])
    
    wb.save(response)
    return response
```

## 9. Modal/Popup (Bootstrap)
```html
<!-- Button -->
<button data-bs-toggle="modal" data-bs-target="#myModal">Open</button>

<!-- Modal -->
<div class="modal fade" id="myModal">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5>Title</h5>
                <button class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">Content here</div>
            <div class="modal-footer">
                <button class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
            </div>
        </div>
    </div>
</div>
```

## 10. AJAX (Load without refresh)
```html
<script>
function loadData() {
    fetch('/api/data/')
        .then(response => response.json())
        .then(data => {
            document.getElementById('result').innerHTML = data.message;
        });
}
</script>
<button onclick="loadData()">Load</button>
<div id="result"></div>
```

```python
# View
from django.http import JsonResponse

def api_data(request):
    return JsonResponse({'message': 'Hello', 'count': 10})
```

## 11. Filter by Date
```python
from datetime import datetime, timedelta

# Today
today = datetime.now().date()
items = MyModel.objects.filter(created_at__date=today)

# Last 7 days
week_ago = today - timedelta(days=7)
items = MyModel.objects.filter(created_at__gte=week_ago)

# Specific month
items = MyModel.objects.filter(created_at__year=2024, created_at__month=1)
```

## 12. Authentication Check
```python
from authentication.guards import session_login_required, role_required

@session_login_required
@role_required("ADMIN", "STAFF")
def my_view(request):
    user_role = request.session.get('auth', {}).get('role_name')
    return render(request, 'template.html')
```

## 13. Messages/Alerts
```python
from django.contrib import messages

def my_view(request):
    messages.success(request, 'Success!')
    messages.error(request, 'Error!')
    messages.warning(request, 'Warning!')
    messages.info(request, 'Info!')
    return redirect('home')
```

```html
<!-- Template -->
{% if messages %}
    {% for message in messages %}
        <div class="alert alert-{{ message.tags }}">{{ message }}</div>
    {% endfor %}
{% endif %}
```

## 14. File Upload
```python
# forms.py
class UploadForm(forms.Form):
    file = forms.FileField()

# views.py
def upload_view(request):
    if request.method == 'POST':
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['file']
            # Save file
            with open(f'uploads/{file.name}', 'wb+') as f:
                for chunk in file.chunks():
                    f.write(chunk)
            return redirect('success')
    else:
        form = UploadForm()
    return render(request, 'upload.html', {'form': form})
```

```html
<form method="post" enctype="multipart/form-data">
    {% csrf_token %}
    {{ form.as_p }}
    <button type="submit">Upload</button>
</form>
```

## 15. Common Template Tags
```html
<!-- Loop -->
{% for item in items %}
    {{ item.name }}
{% empty %}
    No items
{% endfor %}

<!-- If condition -->
{% if user.is_authenticated %}
    Welcome {{ user.name }}
{% else %}
    Please login
{% endif %}

<!-- Date format -->
{{ date|date:"Y-m-d" }}
{{ date|date:"M d, Y" }}

<!-- String operations -->
{{ text|upper }}
{{ text|lower }}
{{ text|title }}
{{ text|truncatewords:10 }}

<!-- Math -->
{{ value|add:5 }}
{{ value|divisibleby:2 }}
```

## 🔥 Most Common Tasks in Tests

1. **Add Print Button** → `<button onclick="window.print()">Print</button>`
2. **Add Search** → Form with `method="get"` + filter in view
3. **Add New Page** → View + URL + Template
4. **Add Form** → forms.py + POST handling + template
5. **Export Excel** → openpyxl + HttpResponse
6. **Add Pagination** → Paginator in view
7. **Add Filter** → GET parameters + query filter
8. **Add Modal** → Bootstrap modal HTML
9. **Add Validation** → Form clean methods
10. **Add Authentication** → @session_login_required decorator

## ⚡ Speed Tips

- Copy existing code and modify it
- Use Bootstrap classes for styling
- Test frequently (run server and check)
- Use {% csrf_token %} in all POST forms
- Always use {% load static %} for static files
- Check urls.py for correct path names
- Use {% url 'name' %} for links

Good luck! 🍀
