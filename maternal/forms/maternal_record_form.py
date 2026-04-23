# maternal/forms/risk_code_form.py
from django import forms
from maternal.forms.maternal_identification_form import add_bootstrap_classes
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository

class RiskCodeForm(forms.Form):
    # Two category checkboxes (editable controls)
    risk_obstetric_history = forms.BooleanField(
        required=False, label="Obstetric history risk(s)"
    )
    risk_medical_comorbidities = forms.BooleanField(
        required=False, label="Medical comorbidity risk(s)"
    )

    def __init__(self, mhr_repo: MaternalHealthRecordRepository, mhr_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._mhr_repo = mhr_repo
        self._mhr_id = mhr_id