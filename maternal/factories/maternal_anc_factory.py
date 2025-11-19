"""Factory helpers to centralize creation of maternal ANC forms and formsets.

Use this factory from views to keep form construction in one place without
changing the form constructors or the frontend behavior.

Example:
    factory = MaternalANCFactory(repository=REPOSITORY, staff_id=staff_id)
    identification_form = factory.create_identification_form(role, maternal_id=record_id)
"""
from typing import Any, Dict, Iterable, List, Optional

from maternal.forms.maternal_identification_form import MaternalIdentificationForm
from maternal.forms.obstetric_history_form import ObstetricHistoryForm
from maternal.forms.medical_history_form import MedicalHistoryForm
from maternal.forms.previous_pregnancy_form import PreviousPregnancyForm, PreviousPregnancyFormSet
from maternal.forms.tetanus_toxoid_form import TetanusToxoidForm
from maternal.forms.present_pregnancy_form import PresentPregnancyForm
from maternal.forms.labolatory_form import LaboratoryForm
from maternal.forms.check_list_form import CheckListForm
from maternal.forms.plans_form import PlanForm
from maternal.forms.micro_nutrients_form import MicroNutrientsForm
from maternal.forms.maternal_record_form import RiskCodeForm
from maternal.forms.pre_natal_follow_up_base_formset import PrenatalFollowUpFormSet
from maternal.forms.pre_natal_follow_up_form import PrenatalFollowUpEntryForm


class MaternalANCFactory:
    """Centralized factory for creating ANC-related forms and formsets.

    The factory keeps the same keyword arguments expected by existing form
    constructors so it can be introduced without changing callers. It accepts
    a repository and optional staff_id to use in calls where appropriate.
    """

    def __init__(self, repository: Any, staff_id: Optional[int] = None):
        self.repository = repository
        self.staff_id = staff_id

    def create_identification_form(self, role: str, maternal_id: Optional[int] = None, data: Optional[Dict] = None):
        return MaternalIdentificationForm(role=role, maternal_repository=self.repository, maternal_id=maternal_id, data=data)

    def create_obstetric_form(self, mhr_id: int, data: Optional[Dict] = None):
        return ObstetricHistoryForm(maternal_repository=self.repository, mhr_id=mhr_id, data=data)

    def create_medical_history_form(self, mhr_id: int, data: Optional[Dict] = None):
        return MedicalHistoryForm(maternal_repository=self.repository, mhr_id=mhr_id, data=data)

    def create_previous_pregnancy_formset(self, initial: Optional[List[Dict]] = None, prefix: str = "pp", mhr_repository: Any = None, maternal_id: Optional[int] = None):
        # keep same signature used by views
        return PreviousPregnancyFormSet(initial=initial or [], prefix=prefix, form_kwargs={"mhr_repository": mhr_repository or self.repository, "maternal_id": maternal_id})

    def create_previous_pregnancy_entry_form(self, maternal_id: int):
        return PreviousPregnancyForm(mhr_repository=self.repository, maternal_id=maternal_id)

    def create_tetanus_toxoid_form(self, mhr_id: int, data: Optional[Dict] = None):
        return TetanusToxoidForm(mhr_repo=self.repository, mhr_id=mhr_id, data=data)

    def create_present_pregnancy_form(self, mhr_id: int, data: Optional[Dict] = None):
        return PresentPregnancyForm(mhr_repo=self.repository, mhr_id=mhr_id, data=data)

    def create_laboratory_form(self, mhr_id: int, data: Optional[Dict] = None, files: Optional[Any] = None):
        form = LaboratoryForm(mhr_repo=self.repository, mhr_id=mhr_id, data=data)
        if files:
            form._raw_files = files
        return form

    def create_checklist_form(self, mhr_id: int, data: Optional[Dict] = None):
        return CheckListForm(mhr_repo=self.repository, mhr_id=mhr_id, data=data)

    def create_plan_form(self, mhr_id: int, data: Optional[Dict] = None):
        return PlanForm(mhr_repo=self.repository, mhr_id=mhr_id, data=data)

    def create_micro_nutrients_form(self, mhr_id: int, data: Optional[Dict] = None):
        return MicroNutrientsForm(mhr_repo=self.repository, mhr_id=mhr_id, data=data)

    def create_risk_code_form(self, mhr_id: int, data: Optional[Dict] = None):
        return RiskCodeForm(mhr_repo=self.repository, mhr_id=mhr_id, data=data)

    def create_prenatal_followup_formset(self, initial: Optional[List[Dict]] = None, prefix: str = "pf", mhr_repository: Any = None, maternal_id: Optional[int] = None):
        return PrenatalFollowUpFormSet(initial=initial or [], prefix=prefix, form_kwargs={"mhr_repository": mhr_repository or None, "maternal_id": maternal_id})

    def create_prenatal_followup_entry_form(self, maternal_id: int, role: Optional[str] = None):
        # PrenatalFollowUpEntryForm may accept role in some contexts (bhw vs midwife)
        kwargs = {"maternal_id": maternal_id, "mhr_repository": self.repository}
        if role is not None:
            kwargs["role"] = role
        return PrenatalFollowUpEntryForm(**kwargs)

    def create_all_for_view(self, record_id: int, role: str, person_id: Optional[int] = None, previous_pregnancies: Optional[Iterable[Dict]] = None, prenatal_existing: Optional[Iterable[Dict]] = None):
        """Convenience helper returning a dict of forms matching the view's context keys.

        This allows the view to call factory.create_all_for_view(...) and get the same
        set of forms used by `maternal_health_record_form` without changing callers.
        """
        # Build previous pregnancy initial data
        prev_rows = previous_pregnancies or []
        prev_initial = [{
            "delivery_date": r.get("date_of_delivery"),
            "outcome": r.get("outcome_type"),
            "delivery_type": r.get("delivery_type"),
            "baby_weight_kg": r.get("baby_weight_kg"),
            "gender": r.get("gender"),
            "ballard_score": r.get("ballard"),
            "apgar_score": r.get("apgar"),
        } for r in prev_rows]

        prenatal_rows = prenatal_existing or []
        prenatal_initial = [{
            "date": r.get("date"),
            "aog_days": r.get("aog_days"),
            "aog_weeks": r.get("aog_weeks"),
            "wt_kg": r.get("weight"),
            "bp_systolic": r.get("bp_systolic"),
            "bp_diastolic": r.get("bp_diastolic"),
            "findings": r.get("leopolds_findings") or 'TBD',
            "notes": r.get("notes") or 'TBD',
        } for r in prenatal_rows]

        return {
            "identification_form": self.create_identification_form(role, maternal_id=record_id),
            "obstetric_form": self.create_obstetric_form(record_id),
            "medical_history_form": self.create_medical_history_form(record_id),
            "formset": self.create_previous_pregnancy_formset(initial=prev_initial, prefix="pp", mhr_repository=self.repository, maternal_id=record_id),
            "previous_pregnancy_entry_form": self.create_previous_pregnancy_entry_form(record_id),
            "tt_form": self.create_tetanus_toxoid_form(record_id),
            "present_pregnancy_form": self.create_present_pregnancy_form(record_id),
            "lab_form": self.create_laboratory_form(record_id),
            "check_list_form": self.create_checklist_form(record_id),
            "plan_form": self.create_plan_form(record_id),
            "micro_nutrients_form": self.create_micro_nutrients_form(record_id),
            "risk_code_form": self.create_risk_code_form(record_id),
            "prenatal_followup_formset": self.create_prenatal_followup_formset(initial=prenatal_initial, prefix="pf", mhr_repository=None, maternal_id=record_id),
            "prenatal_followup_entry_form": self.create_prenatal_followup_entry_form(record_id, role=role),
        }
