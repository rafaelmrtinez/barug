from django import forms
from child_health.repository import ChildHealthRecordRepository
from maternal.forms.maternal_identification_form import add_bootstrap_classes

class IronIntakeForm(forms.Form):
    date_iron_started = forms.CharField(
        label="Date iron started", required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    date_iron_completed = forms.CharField(label="Completed", required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    
    def __init__(self, chr_repo: ChildHealthRecordRepository, child_health_record_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
