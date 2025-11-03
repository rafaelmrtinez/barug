# maternal/forms/risk_code_form.py
from django import forms
from maternal.forms.maternal_identification_form import add_bootstrap_classes
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository

class RiskCodeForm(forms.Form):
    # --- NEW: two category checkboxes (the only editable controls) ---
    risk_obstetric_history = forms.BooleanField(
        required=False, label="Obstetric history risk(s)"
    )
    risk_medical_comorbidities = forms.BooleanField(
        required=False, label="Medical comorbidity risk(s)"
    )

    # --- Keep the original fine-grained flags but hide them from the UI ---
    #     (Set these initials from your DB in the view if you need to preserve values)
    risk_prev_cs = forms.BooleanField(required=False, widget=forms.HiddenInput(), label="Previous C-Section")
    risk_three_miscarriages = forms.BooleanField(required=False, widget=forms.HiddenInput(), label="Three or more miscarriages")
    risk_pph = forms.BooleanField(required=False, widget=forms.HiddenInput(), label="Postpartum hemorrhage")
    risk_tb = forms.BooleanField(required=False, widget=forms.HiddenInput(), label="Tuberculosis")
    risk_heart_disease = forms.BooleanField(required=False, widget=forms.HiddenInput(), label="Heart disease")
    risk_diabetes = forms.BooleanField(required=False, widget=forms.HiddenInput(), label="Diabetes")
    risk_asthma = forms.BooleanField(required=False, widget=forms.HiddenInput(), label="Asthma")
    risk_goiter = forms.BooleanField(required=False, widget=forms.HiddenInput(), label="Goiter")

    assessed_by = forms.CharField(required=False)

    def __init__(self, mhr_repo: MaternalHealthRecordRepository, mhr_id: int, assisted_by: str | None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._mhr_repo = mhr_repo
        self._mhr_id = mhr_id