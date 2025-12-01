from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.core.paginator import Paginator
from django.contrib import messages
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.views.decorators.http import require_http_methods
import json

from authentication.guards import role_required, session_login_required
from authentication.utils import nocache
from barug.utility.lazy_repository import LazyRepositoryProxy
from barug.utility.messages_util import MessageUtility
from src.infra.exceptions.maternal_health_record_exceptions import MaternalHealthRecordException
from maternal.forms.check_list_form import CheckListForm
from maternal.forms.labolatory_form import LaboratoryForm
from maternal.forms.maternal_identification_form import MaternalIdentificationForm
from maternal.forms.maternal_record_form import RiskCodeForm
from maternal.forms.medical_history_form import MedicalHistoryForm
from maternal.forms.mhr_completion_form import MHRCompletionForm
from maternal.forms.micro_nutrients_form import MicroNutrientsForm
from maternal.forms.obstetric_history_form import ObstetricHistoryForm
from maternal.forms.plans_form import PlanForm
from maternal.forms.pre_natal_follow_up_base_formset import PrenatalFollowUpFormSet
from maternal.forms.pre_natal_follow_up_form import PrenatalFollowUpEntryForm
from maternal.forms.present_pregnancy_form import PresentPregnancyForm
from maternal.forms.previous_pregnancy_form import PreviousPregnancyForm, PreviousPregnancyFormSet
from maternal.forms.tetanus_toxoid_form import TetanusToxoidForm
from maternal.forms.postpartum_record_form import PostpartumRecordForm
from maternal.factories.maternal_anc_factory import MaternalANCFactory
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from maternal.utils.form_lock import FormLockUtility
from src.infra.database.connection_adapter import ConnectionAdapter

from src.app.services.laboratory_service import LaboratoryService, LaboratoryTestException
from src.app.services.maternal_risk_service import MaternalRiskService

import logging

from src.infra.repositories.queries.maternal_health_record_queries import MaternalHealthRecordQueries

logger = logging.getLogger(__name__)

# Create your views here.
ACCESS = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")
BHW_ACCESS = ("Barangay Health Worker", "bhw")
MIDWIFE_ACCESS = ("MIDWIFE", "Midwife", "midwife")


REPOSITORY: MaternalHealthRecordRepository = LazyRepositoryProxy(repo_factory=lambda: MaternalHealthRecordRepository(ConnectionAdapter()))
    
@session_login_required
@role_required(*BHW_ACCESS)
@nocache
@csrf_protect
def health_worker_prenatal_form_view(request: HttpRequest, mhr_id: int) -> HttpResponse:
    # Implementation for the health worker prenatal form view
    # Wrap the view logic with robust exception handling so unexpected errors
    # don't surface raw tracebacks to users and we always render a usable form.
    staff_id = request.session.get("auth", {}).get("staff_id")
    staff_role = request.session.get("auth", {}).get("role_name")
    existing_data = REPOSITORY.fetch_prenatal_information_by_mhr_id(mhr_id)
    initial = [{
        "anc_row_id": r.get("anc_row_id"),
        "date":  r.get("date"),
        "aog_days": r.get("aog_days"),
        "aog_weeks": r.get('aog_weeks'),
        "wt_kg": r.get("weight"),
        "bp_systolic": r.get("bp_systolic"),
        "bp_diastolic": r.get("bp_diastolic"),
        "findings": r.get("leopolds_findings") or 'TBD',
        "notes": r.get("notes") or 'TBD',
    } for r in (existing_data or [])]
    pf_formset = PrenatalFollowUpFormSet(
        initial=initial,
        prefix="pf",
        form_kwargs={
            "mhr_repository": None,
            "maternal_id": mhr_id,
        },
    )
    # GET -> show blank form
    prenatal_form = PrenatalFollowUpEntryForm(
        maternal_id=mhr_id,
        mhr_repository=REPOSITORY,
        role=staff_role,
    )
    return render(request, "maternal/bhw_prenatal_form.html", {
        "page_path": "Maternal > Prenatal Form",
        "page_title": "Prenatal Form - Health Worker",
        "prenatal_form": prenatal_form,
        "mhr_id": mhr_id,
        "prenatal_followup_formset": pf_formset,
    })

@session_login_required
@role_required(*ACCESS)
@nocache
@csrf_protect
def find_mother_basic_info(request: HttpRequest, person_id: int) -> JsonResponse:
    basic_info = REPOSITORY.fetch_mother_basic_info_by_person_id(person_id)
    return JsonResponse(basic_info)

@session_login_required
@role_required(*BHW_ACCESS)
@nocache
@csrf_protect
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
                    messages.success(request, f"Maternal identification record created successfully.")
                    # Here you would typically save the data to the database
                    # For now, just redirect or render a success message
                    return render(request, "maternal/identification.html", {
                        "page_path": "Maternal > Identification",
                        "page_title": "Maternal Identification",
                        "identification_form": maternal_identification_form,
                    })
                else:
                    messages.error(request, "Failed to create maternal identification record.")
                    return render(request, "maternal/identification.html", {
                        "page_path": "Maternal > Identification",
                        "page_title": "Maternal Identification",
                        "identification_form": maternal_identification_form,
                    })
            else:
                messages.warning(request, "Please fill out fields with red asterisk.")
                # MessageUtility.push_form_errors_as_messages(request, maternal_identification_form)
                return render(request, "maternal/identification.html", {
                    "page_path": "Maternal > Identification",
                    "page_title": "Maternal Identification",
                    "identification_form": maternal_identification_form,
                })
        else:
            maternal_identification_form = MaternalIdentificationForm(
                role=role,
                maternal_repository=REPOSITORY,
                maternal_id=None
            )
        return render(request, "maternal/identification.html", {
            "page_path": "Maternal > Identification",
            "page_title": "Maternal Identification",
            "identification_form": maternal_identification_form,
        })
    except MaternalHealthRecordException as e:
        logger.warning(f"Error creating maternal entry: {str(e)}")
        messages.warning(request, e.message)
        return render(request, "maternal/identification.html", {
            "page_path": "Maternal > Identification",
            "page_title": "Maternal Identification",
            "identification_form": maternal_identification_form,
        })
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        messages.error(request, f"Something went wrong. Please try again later.")
        return render(request, "maternal/identification.html", {
            "page_path": "Maternal > Identification",
            "page_title": "Maternal Identification",
            "identification_form": maternal_identification_form,
        })

@session_login_required
@role_required(*ACCESS)
@nocache
@csrf_protect
def maternal_health_record_form(request, record_id : int):
    try:
        role = request.session.get("auth", {}).get("role_name")
        assistant = (request.session.get("auth", {}).get("first_name") or "") + " " + (request.session.get("auth", {}).get("last_name") or "")
        staff_id = request.session.get("auth", {}).get("staff_id")

        mhr_status = MHRCompletionForm(repository=REPOSITORY, mhr_id=record_id)
        
        # fetch the current record status row (repo method already exists)
        status_row = REPOSITORY.fetch_maternal_health_record_status_by_mhr_id(record_id) or {}
        status_name = (status_row.get('record_status_name') or "").upper()
        
        # lock when COMPLETE or INCOMPLETE (incomplete semantics you described)
        is_locked = status_name in ('COMPLETE', 'INCOMPLETE')
        
        # Use factory to centralize form creation
        factory = MaternalANCFactory(repository=REPOSITORY, staff_id=staff_id)
        # Ensure prenatal existing data is available for factory (may be used by create_all_for_view)
        pre_natal_existing_data = REPOSITORY.fetch_prenatal_information_by_mhr_id(record_id)
        person_id = REPOSITORY.fetch_person_id_by_maternal_record_id(maternal_record_id=record_id) or None
        # Fetch rows once, then map to form initial
        rows = REPOSITORY.fetch_all_previous_pregnancies_by_person_id(person_id)
        # Map repo fields -> form field names (adjust keys to your repo output)
        
        postpartum_visit_data = MaternalHealthRecordQueries(ConnectionAdapter()).get_postpartum_visit_rows_with_feeding_type_by_mhr_id(record_id)
        initial = [{
            "delivery_date":  r.get("date_of_delivery"),
            "outcome":   r.get("outcome_type"),
            "delivery_type":  r.get('delivery_type'),  # if your choices expect an ID
            "baby_weight_kg": r.get("baby_weight_kg"),
            "gender":         r.get("gender"),          # align with GENDER_CHOICES values
            "ballard_score":  r.get("ballard"),
            "apgar_score":    r.get("apgar"),
        } for r in (rows or [])]
        formset = PreviousPregnancyFormSet(
            initial=initial,
            prefix="pp",
            form_kwargs={"mhr_repository": REPOSITORY, "maternal_id": record_id},  # <-- pass to each form
        )
        # single-entry form for adding a previous pregnancy (user adds one-by-one)
        # Build forms via factory so we keep construction logic in one place.
        created = factory.create_all_for_view(
            record_id=record_id,
            role=role,
            person_id=person_id,
            previous_pregnancies=rows,
            prenatal_existing=pre_natal_existing_data,
        )

        maternal_identification_form = created.get('identification_form')
        obstetric_form = created.get('obstetric_form')
        medical_history_form = created.get('medical_history_form')
        formset = created.get('formset')
        pp_entry_form = created.get('previous_pregnancy_entry_form')
        tt_form = created.get('tt_form')
        presemt_pregnancy_form = created.get('present_pregnancy_form')
        lab_form = created.get('lab_form')
        check_list_form = created.get('check_list_form')
        plan_form = created.get('plan_form')
        micro_nutrients_form = created.get('micro_nutrients_form')
        risk_code_form = created.get('risk_code_form')
        pf_formset = created.get('prenatal_followup_formset')
        pf_entry_form = created.get('prenatal_followup_entry_form')
        # Prefill risk_code_form initial values from repository
        try:
            _risk_rows = REPOSITORY.fetch_risk_codes_by_mhr_id(record_id) or []
            # Map the two categories to our form fields
            for r in _risk_rows:
                cat = (r.get('category') or '').upper()
                is_present = bool(r.get('is_present'))
                if cat == 'OBSTETRIC RISKS':
                    risk_code_form.fields['risk_obstetric_history'].initial = is_present
                    risk_code_form.initial['risk_obstetric_history'] = is_present
                elif cat == 'MEDICAL CONDITIONS':
                    risk_code_form.fields['risk_medical_comorbidities'].initial = is_present
                    risk_code_form.initial['risk_medical_comorbidities'] = is_present
            # expose flag for template/JS to know if existing entries exist
            risk_code_form.has_existing = any(r.get('is_present') for r in _risk_rows)
        except Exception:
            # If fetch fails, do not block rendering; log and continue
            logger.exception('Unable to load existing risk codes for mhr_id=%s', record_id)
            risk_code_form.has_existing = False
        
        pre_natal_existing_data = REPOSITORY.fetch_prenatal_information_by_mhr_id(record_id)
        print(f'pre_natal_existing_data: {pre_natal_existing_data}')
        initial_pre_natal_existing_data = [{
            "anc_row_id": r.get("anc_row_id"),
            "date":  r.get("date"),
            "aog_days": r.get("aog_days"),
            "aog_weeks": r.get('aog_weeks'),
            "wt_kg": r.get("weight"),
            "bp_systolic": r.get("bp_systolic"),
            "bp_diastolic": r.get("bp_diastolic"),
            "findings": r.get("leopolds_findings") or 'TBD',
            "notes": r.get("notes") or 'TBD',
        } for r in (pre_natal_existing_data or [])]
        
        # NEW: Prenatal follow-up formset (DB not ready → no initial yet)
        # keep the same prefix "pf" you used in POST
        pf_formset = PrenatalFollowUpFormSet(
            initial=initial_pre_natal_existing_data,
            prefix="pf",
            form_kwargs={
                "mhr_repository": None,
                "maternal_id": record_id,
                "role": role,
            },
        )
        # single blank form for entering a new prenatal followup
        pf_entry_form = PrenatalFollowUpEntryForm(
            mhr_repository=REPOSITORY,
            maternal_id=record_id,
            role=role,
            prefix="pf_entry"  # keep prefixes distinct from the formset (if used)
        )

        # The view no longer accepts POST for saving forms. POST handling
        # was moved into separate class-based API endpoints under
        # `maternal/api/`. Only display (GET) is allowed here.
        if request.method != 'GET':
            return HttpResponse(status=405)
        
        logger.info(f"FORM TYPE RECEIVED: {request.POST.get('form_type', None)}")
        return render(request, "maternal/health_record_form.html", {
            "page_path": "Maternal > Health Record",
            "page_title": "Maternal Health Record Form",
            "postpartum_visit_data": postpartum_visit_data,
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
            "previous_pregnancy_entry_form": pp_entry_form,
            "prenatal_followup_entry_form": pf_entry_form,
            "prenatal_followup_formset": pf_formset,
            "mhr_id": record_id,
            "mhr_status": mhr_status,
            "is_locked": is_locked,
        })
    except MaternalHealthRecordException as e:
        logger.warning(f"Error in maternal health record form: {str(e)}")
        messages.warning(request, e.message)
        return render(request, "maternal/health_record_form.html", {
            "page_path": "Maternal > Health Record",
            "page_title": "Maternal Health Record Form",
            "postpartum_visit_data": postpartum_visit_data,
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
            "previous_pregnancy_entry_form": pp_entry_form,
            "prenatal_followup_entry_form": pf_entry_form,
            "prenatal_followup_formset": pf_formset,
            "mhr_id": record_id,
            "mhr_status": mhr_status,
            "is_locked": is_locked,
        })
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        messages.error(request, f"Something went wrong. Please try again later.")
        return redirect('maternal:maternal_health_record_form', record_id=record_id)

@session_login_required
@role_required(*MIDWIFE_ACCESS)
@nocache
@csrf_protect
def laboratory_save_api(request, record_id: int) -> JsonResponse:
    """AJAX endpoint to save laboratory data.

    Expects JSON payload (or form-encoded fields) containing the laboratory form fields.
    Validates the payload using the LaboratoryForm (calls `is_clean()` if present,
    otherwise falls back to `is_valid()`), calls the LaboratoryService, and returns
    a JSON response indicating success or failure.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Only POST allowed.'}, status=405)

    deny = FormLockUtility.deny_if_locked(request, REPOSITORY, record_id, api=True)
    if deny:
        return deny

    # parse payload: prefer JSON body, fall back to POST dict
    payload = {}
    try:
        if request.content_type and request.content_type.startswith('application/json'):
            payload = json.loads(request.body.decode('utf-8') or '{}')
        else:
            # QueryDict -> normal dict (handles form-encoded or multipart without files)
            payload = {k: v for k, v in request.POST.items()}
    except Exception as e:
        logger.exception('Failed to parse request payload for laboratory_save_api')
        return JsonResponse({'success': False, 'message': 'Invalid JSON payload.'}, status=400)

    # instantiate form with payload (no files expected in this JSON flow)
    lab_form = LaboratoryForm(mhr_repo=REPOSITORY, mhr_id=record_id, data=payload)
    # attach files if present (e.g., when frontend uses FormData)
    if request.FILES:
        lab_form._raw_files = request.FILES

    # Prefer calling is_clean() if the form exposes it (user requested),
    # otherwise fall back to the standard is_valid().
    try:
        is_clean_method = getattr(lab_form, 'is_clean', None)
        if callable(is_clean_method):
            valid = lab_form.is_clean()
        else:
            valid = lab_form.is_valid()
    except Exception:
        logger.exception('Error during form validation in laboratory_save_api')
        return JsonResponse({'success': False, 'message': 'Validation error.'}, status=400)

    if not valid:
        # return form errors as JSON so the frontend can alert the user
        return JsonResponse({'success': False, 'errors': lab_form.errors}, status=400)

    # extract paired tests produced by the form's clean() and call service
    paired = lab_form.cleaned_data.get('paired_tests') if hasattr(lab_form, 'cleaned_data') else getattr(lab_form, 'paired_tests', [])
    svc = LaboratoryService(REPOSITORY, request.session.get('auth', {}).get('staff_id'), record_id)
    try:
        result = svc.save(paired)
    except (LaboratoryTestException, MaternalHealthRecordException) as e:
        # Client attempted to add/upload tests that already exist
        logger.info('Client attempted to add existing lab tests: %s', getattr(e, 'tests', None))
        return JsonResponse({'success': False, 'message': str(e), 'conflicts': getattr(e, 'tests', [])}, status=409)
    except Exception:
        logger.exception('Unexpected error while saving laboratory data (API)')
        return JsonResponse({'success': False, 'message': 'Something went wrong while saving Laboratory data.'}, status=500)

    if isinstance(result, dict):
        success = bool(result.get('success'))
        details = result.get('res')
    else:
        success = bool(result)
        details = None

    if not success:
        return JsonResponse({'success': False, 'message': 'Failed to save Laboratory data.', 'details': details}, status=500)

    return JsonResponse({'success': True, 'message': 'Laboratory data saved successfully.'})

@session_login_required
@role_required(*ACCESS)
@nocache
@csrf_protect
def record_detail(request: HttpRequest, person_id: int) -> HttpResponse:
    maternal_health_record_id = REPOSITORY.fetch_maternal_health_record_id_by_person_id(person_id)['maternal_record_id']
    record = REPOSITORY.fetch_latest_maternal_record_by_person_and_maternal_id(person_id, maternal_record_id=maternal_health_record_id) or {}
    all_records = REPOSITORY.fetch_all_maternal_records_for_person(person_id)
    basic_info = REPOSITORY.fetch_mhr_count_and_fam_id_by_person_id(person_id)
    staff_name = (request.session.get('auth', {}).get('first_name') or "") + ' ' + (request.session.get('auth', {}).get('last_name') or "")
    # prepare postpartum form pre-populated with maternal record id
    postpartum_form = PostpartumRecordForm(
        mhr_id=maternal_health_record_id,
        role=request.session.get('auth', {}).get('role_name'),
        staff_name=staff_name,
        staff_id=request.session.get('auth', {}).get('staff_id'),
        repository=REPOSITORY,
    )

    return render(
        request,
        "maternal/record_history.html",
        {
            "page_path": "Maternal > Record History",
            "page_title": "Maternal Record History",
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
            "basic_info": basic_info,
            "postpartum_form": postpartum_form,
        },
    )

@session_login_required
@role_required(*ACCESS)
@nocache
@csrf_protect
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
            "page_path": "Maternal > Records",
            "page_title": "Maternal Records",
            "q": q,
            "page_obj": page_obj,
        },
    )
