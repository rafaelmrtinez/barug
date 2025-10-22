from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.core.paginator import Paginator
from django.contrib import messages
from django.views.decorators.csrf import csrf_protect as csrf_required

from authentication.guards import role_required, session_login_required
from authentication.utils import nocache
from barug.utility.messages_util import MessageUtility
from maternal.exceptions.maternal_exceptions import MaternalHealthRecordException
from maternal.forms.check_list_form import CheckListForm
from maternal.forms.labolatory_form import LaboratoryForm
from maternal.forms.maternal_identification_form import MaternalIdentificationForm
from maternal.forms.maternal_record_form import RiskCodeForm
from maternal.forms.medical_history_form import MedicalHistoryForm
from maternal.forms.micro_nutrients_form import MicroNutrientsForm
from maternal.forms.obstetric_history_form import ObstetricHistoryForm
from maternal.forms.plans_form import PlanForm
from maternal.forms.pre_natal_follow_up_base_formset import PrenatalFollowUpFormSet
from maternal.forms.present_pregnancy_form import PresentPregnancyForm
from maternal.forms.previous_pregnancy_form import PreviousPregnancyFormSet
from maternal.forms.tetanus_toxoid_form import TetanusToxoidForm
from maternal.repository import MaternalHealthRecordRepository
from midwife.services import fetch_maternal_registry
from src.infra.database.connection_adapter import ConnectionAdapter

import logging

logger = logging.getLogger(__name__)

# Create your views here.
ACCESS = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")
ADAPTER = ConnectionAdapter()
REPOSITORY = MaternalHealthRecordRepository(ADAPTER)

@session_login_required
@role_required(*ACCESS)
@nocache
@csrf_required
def find_mother_basic_info(request: HttpRequest, person_id: int) -> JsonResponse:
    basic_info = REPOSITORY.fetch_mother_basic_info_by_person_id(person_id)
    return JsonResponse(basic_info)

@session_login_required
@role_required(*ACCESS)
@nocache
@csrf_required
def create_new_maternal_entry(request: HttpRequest) -> HttpResponse:
    try:
        role = request.session.get("auth", {}).get("role_name")
        staff_id = request.session.get("auth", {}).get("staff_id")
        if request.method == "POST":
            maternal_identification_form = MaternalIdentificationForm(
                data=request.POST,
                role=role,
                maternal_repository=REPOSITORY,
                maternal_id=None
            )
            if maternal_identification_form.is_valid():
                # Process the valid form data
                data = maternal_identification_form.cleaned_data
                print(f"Valid Maternal Identification Data: {data}")
                res = REPOSITORY.insert_maternal_health_record(
                    staff_id=staff_id,
                    person_id=data.get("person_id"),
                    husband_id=data.get("husband_id"),
                    weight=data.get("weight_kg"),
                    height=data.get("height_cm"),
                    bmi_status_id=data.get("bmi_status_id"),
                    is_transferred=data.get("is_transferred", False),
                )
                if res:
                    if res.get("create_maternal_health_record_bhw"):
                        res = f"Maternal Record ID: {res.get('maternal_record_id')}"                
                        messages.success(request, f"Maternal identification record created successfully. {res}")
                        # Here you would typically save the data to the database
                        # For now, just redirect or render a success message
                        return render(request, "maternal/identification.html", {
                            "identification_form": maternal_identification_form,
                        })
                else:
                    messages.error(request, "Failed to create maternal identification record.")
                    return render(request, "maternal/identification.html", {
                        "identification_form": maternal_identification_form,
                    })
            else:
                messages.warning(request, "Please fill out fields with red asterisk.")
                # MessageUtility.push_form_errors_as_messages(request, maternal_identification_form)
                return render(request, "maternal/identification.html", {
                    "identification_form": maternal_identification_form,
                })
        else:
            maternal_identification_form = MaternalIdentificationForm(
                role=role,
                maternal_repository=REPOSITORY,
                maternal_id=None
            )
        return render(request, "maternal/identification.html", {
            "identification_form": maternal_identification_form,
        })
    except MaternalHealthRecordException as e:
        logger.warning(f"Error creating maternal entry: {str(e)}")
        messages.warning(request, e.message)
        return render(request, "maternal/identification.html", {
            "identification_form": maternal_identification_form,
        })
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        messages.error(request, f"Something went wrong. Please try again later.")
        return render(request, "maternal/identification.html", {
            "identification_form": maternal_identification_form,
        })

@session_login_required
@role_required(*ACCESS)
@nocache
@csrf_required
def maternal_health_record_form(request, record_id : int):
    role = request.session.get("auth", {}).get("role_name")
    assistant = request.session.get("auth", {}).get("first_name") + " " + request.session.get("auth", {}).get("last_name")
    if request.method == "POST":
        risk_code_form = RiskCodeForm(request.POST)
        formset = PreviousPregnancyFormSet(request.POST, prefix="pp")
        if risk_code_form.is_valid() and formset.is_valid():
            # Save or process
            pass
    else:
        maternal_identification_form = MaternalIdentificationForm(
            role=role, maternal_repository=REPOSITORY, maternal_id=record_id)
        obstetric_form = ObstetricHistoryForm(
            maternal_repository=REPOSITORY,
            mhr_id=record_id
        )
        medical_history_form = MedicalHistoryForm(
            maternal_repository=REPOSITORY,
            mhr_id=record_id
        )
        person_id = REPOSITORY.fetch_person_id_by_maternal_record_id(record_id)
        # Fetch rows once, then map to form initial
        rows = REPOSITORY.fetch_all_previous_pregnancies_by_person_id(person_id)
        # Map repo fields -> form field names (adjust keys to your repo output)
        initial = [{
            "delivery_date":  r.get("date_of_delivery"),
            "outcome":        r.get("outcome_type"),
            "delivery_type":  r.get("delivery_type_id"),  # if your choices expect an ID
            "baby_weight_kg": r.get("baby_weight_kg"),
            "gender":         r.get("baby_sex"),          # align with GENDER_CHOICES values
            "ballard_score":  r.get("ballard"),
            "apgar_score":    r.get("apgar"),
        } for r in (rows or [])]
        formset = PreviousPregnancyFormSet(
            initial=initial,
            prefix="pp",
            form_kwargs={"mhr_repository": REPOSITORY, "maternal_id": record_id},  # <-- pass to each form
        )
        tt_form = TetanusToxoidForm(
            mhr_repo=REPOSITORY,
            mhr_id=record_id
        )
        presemt_pregnancy_form = PresentPregnancyForm(
            mhr_repo=REPOSITORY,
            mhr_id=record_id
        )
        lab_form = LaboratoryForm(
            mhr_repo=REPOSITORY,
            mhr_id=record_id
        )
        check_list_form = CheckListForm(
            mhr_repo=REPOSITORY,
            mhr_id=record_id
        )
        plan_form = PlanForm(
            mhr_repo=REPOSITORY,
            mhr_id=record_id
        )
        micro_nutrients_form = MicroNutrientsForm(
            mhr_repo=REPOSITORY,
            mhr_id=record_id
        )
        risk_code_form = RiskCodeForm(
            mhr_repo=REPOSITORY,
            mhr_id=record_id,
            assisted_by=assistant
        )
        # NEW: Prenatal follow-up formset (DB not ready → no initial yet)
        # keep the same prefix "pf" you used in POST
        pf_formset = PrenatalFollowUpFormSet(
            initial=[],           # will be populated later from your logs table
            prefix="pf",
            form_kwargs={
                "mhr_repository": None,     # supply repo later
                "maternal_id": record_id,
            },
        )
    return render(request, "maternal/health_record_form.html", {
        "risk_code_form": risk_code_form,
        "formset": formset,
        "identification_form": maternal_identification_form,
        "obstetric_form": obstetric_form,
        "medical_history_form": medical_history_form,
        "tt_form": tt_form,
        "present_pregnancy_form": presemt_pregnancy_form,
        "lab_form": lab_form,
        "check_list_form": check_list_form,
        "plan_form": plan_form,
        "micro_nutrients_form": micro_nutrients_form,
    })

@session_login_required
@role_required(*ACCESS)
@nocache
@csrf_required
def record_detail(request: HttpRequest, person_id: int) -> HttpResponse:
    repo = MaternalHealthRecordRepository(ConnectionAdapter())
    maternal_health_record_id = repo.fetch_maternal_health_record_id_by_person_id(person_id)['maternal_record_id']
    record = repo.fetch_latest_maternal_record_by_person_and_maternal_id(person_id, maternal_record_id=maternal_health_record_id) or {}
    all_records = repo.fetch_all_maternal_records_for_person(person_id)
    print(f"All Records: {all_records}")
    return render(
        request,
        "maternal/record_history.html",
        {
            "page_path": "Midwife / Record Details",
            "page_title": "Record Details",
            "record_id": maternal_health_record_id,
            "person_id": person_id,

            # header fields
            "person_name": record.get("full_name"),
            "mhr_number": record.get("maternal_record_id"),
            "family_no":  record.get("family_num"),
            "lmp":        record.get("lmp"),
            "edd":        record.get("edd"),
            "person_status": record.get("person_status"),

            # history table (now includes latest)
            "all_records": all_records,
        },
    )

@session_login_required
@role_required(*ACCESS, "Super Admin")
@nocache
@csrf_required
def records(request: HttpRequest) -> HttpResponse:
    q = (request.GET.get("q") or "").strip()

    repo = MaternalHealthRecordRepository(ConnectionAdapter())
    rows = repo.fetch_all_most_recent_records() or []  # list[dict] like the sample you showed

    # Optional: simple search filter on the in-memory list (name/family/address)
    if q:
        q_lower = q.lower()
        rows = [
            r for r in rows
            if q_lower in (r.get("full_name","").lower())
            or q_lower in (r.get("family_num","").lower())
            or q_lower in (r.get("full_address","").lower())
        ]

    page_obj = Paginator(rows, 10).get_page(request.GET.get("page"))

    return render(
        request,
        "maternal/records.html",
        {
            "page_title": "Records",
            "q": q,
            "page_obj": page_obj,
        },
    )
