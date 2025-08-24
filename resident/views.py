from django.shortcuts import render
from django.core.paginator import Paginator
from .forms import ResidentProfileform
from .forms import HouseholdProfileForm
from .forms import FamilyProfileForm

from django.conf import settings
from django.http import FileResponse, Http404
from django.contrib.auth.decorators import login_required
from .utils.pdf_forms import fill_pdf_fields


#need back-end for proper assignment
user_fullname = 'lname, fname mname suffix'
user_role = 'Clerk'

user_role_template = user_role.lower().replace(' ', '_')

# Create your views here.
def register_resident(request):
    return render(request, "resident_profiling/register_resident.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Register Resident',
        'page_title' : 'Register Resident',
        'user_role_template' : user_role_template,
    })

def personal_info(request):
    form = ResidentProfileform()

    return render(request, "resident_profiling/personal_info.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Register Resident / Personal Information',
        'page_title' : 'Personal Information',
        'user_role_template' : user_role_template,
        'form' : form,
    })

def socioeconomic_info(request):
    form = ResidentProfileform()

    return render(request, "resident_profiling/socioeconomic_info.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Register Resident / Socioeconomic Information',
        'page_title' : 'Socioeconomic Information',
        'user_role_template' : user_role_template,
        'form' : form,
    })

def supporting_documents(request):
    form = ResidentProfileform()

    return render(request, "resident_profiling/supporting_documents.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Register Resident / Supporting Documents',
        'page_title' : 'Supporting Documents',
        'user_role_template' : user_role_template,
        'form' : form,
    })

def review_info(request):
    return render(request, "resident_profiling/review_info.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f"{user_role} / Resident Management / Register Resident / Review Resident's Information" ,
        'page_title' : "Review Resident's Information",
        'user_role_template' : user_role_template,
    })

def resident_records(request):
    # item_list = MyModel.objects.all()
    # paginator = Paginator(item_list, 10)

    # page_number = request.GET.get('page')
    # page_obj = paginator.get_page(page_number)

    return render(request, 'resident_profiling/resident_records.html', {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Resident Records',
        'page_title' : 'Resident Records',
        'user_role_template' : user_role_template,
        # 'page_obj' : page_obj,
    })

def resident_record(request, res_id):
    form = ResidentProfileform()

    for field in form.fields.values():
        field.disabled = True
        field.widget.attrs['class'] = 'form-control editable-field'

    return render(request, 'resident_profiling/resident_record.html', {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Resident Records / Resident : {res_id}',
        'page_title' : f'Resident : {res_id}',
        'user_role_template' : user_role_template,
        'form' : form,
    })

def household_info(request):
    form = HouseholdProfileForm()

    return render(request, 'household_profiling/household_info.html', {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Resident Records',
        'page_title' : 'Resident Records',
        'user_role_template' : user_role_template,
        'form' : form,
    })

def family_info(request):
    form = FamilyProfileForm()

    return render(request, 'household_profiling/family_info.html', {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Resident Management / Resident Records',
        'page_title' : 'Resident Records',
        'user_role_template' : user_role_template,
        'form' : form,
    })

# OPTIONAL: flatten
# from .utils.pdf_flatten import flatten_filled_pdf

def generate_residency_certificate(request, request_document_id: int):
    """
    Generates a Barangay Residency PDF for an APPROVED & PAID request.
    """
    # --- Replace this with your real ORM lookups ---
    # rd = RequestDocument.objects.select_related("person", "status", "payment").get(pk=request_document_id)
    # if rd.doc_type.code != "BARANGAY_RESIDENCY" or rd.status.code != "APPROVED" or not rd.payment.or_number:
    #     raise Http404("Request not ready for generation.")
    # data = {
    #     "recipient":  rd.person.full_name_upper,
    #     "requestor":  rd.person.full_name_upper,
    #     "application": (rd.purpose or "").upper(),
    #     "date":       rd.approval_date.strftime("%B %d, %Y").upper(),
    #     "month_year": rd.approval_date.strftime("%B %Y").upper(),
    # }

    # --- Demo data so you can test now ---
    data = {
        "recipient":  "JUAN DELA CRUZ",
        "requestor":  "JUAN DELA CRUZ",
        "application":"PASSPORT APPLICATION",
        "date":       "AUGUST 24, 2025",
        "month_year": "AUGUST 2025",
    }

    tpl = settings.BARANGAY_RESIDENCY_TEMPLATE
    filled = fill_pdf_fields(tpl, data)

    # If you want editable (form remains): return `filled`
    # If you want non-editable: uncomment the flatten import and this line:
    # filled = flatten_filled_pdf(filled, data)

    filename = f"Residency_{data['recipient'].replace(' ', '_')}.pdf"
    return FileResponse(filled, as_attachment=True, filename=filename, content_type="application/pdf")
