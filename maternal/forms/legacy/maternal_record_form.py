# maternal/forms/risk_code_form.py
from django import forms
from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.repository import MaternalHealthRecordRepository

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
        self.fields['assessed_by'].disabled = True
        risk_data = mhr_repo.fetch_risk_codes_by_mhr_id(int(mhr_id))
        print(f"Risk data in form init: {risk_data}")
        if risk_data:
            if risk_data[0].get('category') == 'OBSTETRIC RISKS':
                self.fields['risk_obstetric_history'].initial = True
            if risk_data[0].get('category') == 'MEDICAL CONDITIONS':
                self.fields['risk_medical_comorbidities'].initial = True

        
        print(f"Assisted by in form init: {assisted_by}")            
        if assisted_by:
            # disable
            self.fields['assessed_by'].initial = assisted_by
        
