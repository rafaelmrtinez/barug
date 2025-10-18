from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.core.paginator import Paginator

from authentication.guards import role_required, session_login_required
from authentication.utils import nocache
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

# Create your views here.
ACCESS = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")
ADAPTER = ConnectionAdapter()
REPOSITORY = MaternalHealthRecordRepository(ADAPTER)


# @session_login_required
# @role_required(*ACCESS)
# @nocache
# def maternal_health_record_form(request, maternal_id: int):
#     role = request.session.get("auth", {}).get("role_name")
#     assistant = request.session.get("auth", {}).get("first_name") + " " + request.session.get("auth", {}).get("last_name")
#     if request.method == "POST":
#         risk_code_form = RiskCodeForm(request.POST)
#         formset = PreviousPregnancyFormSet(request.POST, prefix="pp")
#         if risk_code_form.is_valid() and formset.is_valid():
#             # Save or process
#             pass
#     else:
#         maternal_identification_form = MaternalIdentificationForm(role=role, maternal_repository=MaternalHealthRecordRepository(ConnectionAdapter()), maternal_id=maternal_id)
#         obstetric_form = ObstetricHistoryForm(
#             maternal_repository=MaternalHealthRecordRepository(ConnectionAdapter()),
#             mhr_id=maternal_id
#         )
#         medical_history_form = MedicalHistoryForm(
#             maternal_repository=MaternalHealthRecordRepository(ConnectionAdapter()),
#             mhr_id=maternal_id
#         )
#         repo = MaternalHealthRecordRepository(ConnectionAdapter())
#         person_id = repo.fetch_person_id_by_maternal_record_id(maternal_id)
#         # Fetch rows once, then map to form initial
#         rows = repo.fetch_all_previous_pregnancies_by_person_id(person_id)
#         # Map repo fields -> form field names (adjust keys to your repo output)
#         initial = [{
#             "delivery_date":  r.get("date_of_delivery"),
#             "outcome":        r.get("outcome_type"),
#             "delivery_type":  r.get("delivery_type_id"),  # if your choices expect an ID
#             "baby_weight_kg": r.get("baby_weight_kg"),
#             "gender":         r.get("baby_sex"),          # align with GENDER_CHOICES values
#             "ballard_score":  r.get("ballard"),
#             "apgar_score":    r.get("apgar"),
#         } for r in (rows or [])]
#         formset = PreviousPregnancyFormSet(
#             initial=initial,
#             prefix="pp",
#             form_kwargs={"mhr_repository": repo, "maternal_id": maternal_id},  # <-- pass to each form
#         )
#         tt_form = TetanusToxoidForm(
#             mhr_repo=MaternalHealthRecordRepository(ConnectionAdapter()),
#             mhr_id=maternal_id
#         )
#         presemt_pregnancy_form = PresentPregnancyForm(
#             mhr_repo=MaternalHealthRecordRepository(ConnectionAdapter()),
#             mhr_id=maternal_id
#         )
#         lab_form = LaboratoryForm(
#             mhr_repo=MaternalHealthRecordRepository(ConnectionAdapter()),
#             mhr_id=maternal_id
#         )
#         check_list_form = CheckListForm(
#             mhr_repo=MaternalHealthRecordRepository(ConnectionAdapter()),
#             mhr_id=maternal_id
#         )
#         plan_form = PlanForm(
#             mhr_repo=MaternalHealthRecordRepository(ConnectionAdapter()),
#             mhr_id=maternal_id
#         )
#         micro_nutrients_form = MicroNutrientsForm(
#             mhr_repo=MaternalHealthRecordRepository(ConnectionAdapter()),
#             mhr_id=maternal_id
#         )
#         risk_code_form = RiskCodeForm(
#             mhr_repo=MaternalHealthRecordRepository(ConnectionAdapter()),
#             mhr_id=maternal_id,
#             assisted_by=assistant
#         )
#         # NEW: Prenatal follow-up formset (DB not ready → no initial yet)
#         # keep the same prefix "pf" you used in POST
#         pf_formset = PrenatalFollowUpFormSet(
#             initial=[],           # will be populated later from your logs table
#             prefix="pf",
#             form_kwargs={
#                 "mhr_repository": None,     # supply repo later
#                 "maternal_id": maternal_id,
#             },
#         )
#     return render(request, "maternal/health_record_form.html", {
#         "risk_code_form": risk_code_form,
#         "formset": formset,
#         "identification_form": maternal_identification_form,
#         "obstetric_form": obstetric_form,
#         "medical_history_form": medical_history_form,
#         "tt_form": tt_form,
#         "present_pregnancy_form": presemt_pregnancy_form,
#         "lab_form": lab_form,
#         "check_list_form": check_list_form,
#         "plan_form": plan_form,
#         "micro_nutrients_form": micro_nutrients_form,
#     })

@session_login_required
@role_required(*ACCESS)
@nocache
def maternal_health_record_form(request: HttpRequest):
    maternal_id = 1
    role = request.session.get("auth", {}).get("role_name") or ""
    assistant = (
        (request.session.get("auth", {}).get("first_name") or "") + " " +
        (request.session.get("auth", {}).get("last_name") or "")
    ).strip()
    print(f"URL {request.path_info}")
    repo = MaternalHealthRecordRepository(ConnectionAdapter())

    if request.method == "POST":
        # Bind POSTed forms/formsets
        risk_code_form = RiskCodeForm(request.POST)
        formset = PreviousPregnancyFormSet(request.POST, prefix="pp")

        # Prenatal Follow-up FormSet (POST: bind data, pass role etc. as TOP-LEVEL kwargs)
        pf_formset = PrenatalFollowUpFormSet(
            request.POST,
            prefix="pf",
            role=role,                 # handled by PrenatalFollowUpBaseFormSet.__init__
            mhr_repository=REPOSITORY,
            maternal_id=maternal_id,
        )

        # Rebuild the OTHER forms so template can render on POST (even with errors)
        maternal_identification_form = MaternalIdentificationForm(role=role, maternal_repository=REPOSITORY, maternal_id=maternal_id)
        obstetric_form = ObstetricHistoryForm(maternal_repository=REPOSITORY, mhr_id=maternal_id)
        medical_history_form = MedicalHistoryForm(maternal_repository=REPOSITORY, mhr_id=maternal_id)
        tt_form = TetanusToxoidForm(mhr_repo=REPOSITORY, mhr_id=maternal_id)
        present_pregnancy_form = PresentPregnancyForm(mhr_repo=REPOSITORY, mhr_id=maternal_id)
        lab_form = LaboratoryForm(mhr_repo=REPOSITORY, mhr_id=maternal_id)
        check_list_form = CheckListForm(mhr_repo=REPOSITORY, mhr_id=maternal_id)
        plan_form = PlanForm(mhr_repo=REPOSITORY, mhr_id=maternal_id)
        micro_nutrients_form = MicroNutrientsForm(mhr_repo=REPOSITORY, mhr_id=maternal_id)

        if risk_code_form.is_valid() and formset.is_valid() and pf_formset.is_valid():
            # TODO: save work
            pass

    else:
        # GET: unbound forms/formsets (load initials later from DB)
        risk_code_form = RiskCodeForm(mhr_repo=REPOSITORY, mhr_id=maternal_id, assisted_by=assistant)
        maternal_identification_form = MaternalIdentificationForm(path=request.path_info, role=role, maternal_repository=REPOSITORY, maternal_id=maternal_id)
        obstetric_form = ObstetricHistoryForm(maternal_repository=REPOSITORY, mhr_id=maternal_id)
        medical_history_form = MedicalHistoryForm(maternal_repository=REPOSITORY, mhr_id=maternal_id)

        formset = PreviousPregnancyFormSet(
            initial=[],
            prefix="pp",
            form_kwargs={"mhr_repository": repo, "maternal_id": maternal_id},
        )

        tt_form = TetanusToxoidForm(mhr_repo=REPOSITORY, mhr_id=maternal_id)
        present_pregnancy_form = PresentPregnancyForm(mhr_repo=REPOSITORY, mhr_id=maternal_id)
        lab_form = LaboratoryForm(mhr_repo=REPOSITORY, mhr_id=maternal_id)
        check_list_form = CheckListForm(mhr_repo=REPOSITORY, mhr_id=maternal_id)
        plan_form = PlanForm(mhr_repo=REPOSITORY, mhr_id=maternal_id)
        micro_nutrients_form = MicroNutrientsForm(mhr_repo=REPOSITORY, mhr_id=maternal_id)

        # Prenatal Follow-up FormSet (GET: unbound, with initial=[], pass kwargs TOP-LEVEL)
        pf_formset = PrenatalFollowUpFormSet(
            prefix="pf",
            role=role,
            mhr_repository=REPOSITORY,
            maternal_id=maternal_id,
            initial=[],   # replace with DB-mapped rows later
        )
        
        prenatal_followup_entry_form = pf_formset.empty_form

    return render(request, "maternal/health_record_form.html", {
        "risk_code_form": risk_code_form,
        "formset": formset,
        "identification_form": maternal_identification_form,
        "obstetric_form": obstetric_form,
        "medical_history_form": medical_history_form,
        "tt_form": tt_form,
        "present_pregnancy_form": present_pregnancy_form,
        "lab_form": lab_form,
        "check_list_form": check_list_form,
        "plan_form": plan_form,
        "micro_nutrients_form": micro_nutrients_form,
        "prenatal_followup_formset": pf_formset,
        "prenatal_followup_entry_form": prenatal_followup_entry_form,
    })

@session_login_required
@role_required(*ACCESS)
@nocache
def record_detail(request: HttpRequest, person_id: int, record_id: int) -> HttpResponse:
    repo = MaternalHealthRecordRepository(ConnectionAdapter())

    # Header summary (you already have this)
    record = repo.fetch_latest_maternal_record_by_person_and_maternal_id(person_id, record_id) or {}
    
    print("RECORD DETAIL:", record)

    # All maternal episodes for this person (includes the latest one)
    all_records = repo.fetch_all_maternal_records_for_person(person_id)

    return render(
        request,
        "maternal/record_history.html",
        {
            "page_path": "Midwife / Record Details",
            "page_title": "Record Details",
            "record_id": record_id,
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
