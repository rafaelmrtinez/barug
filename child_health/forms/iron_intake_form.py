from django import forms
from child_health.repository import ChildHealthRecordRepository
from maternal.forms.maternal_identification_form import add_bootstrap_classes

class IronIntakeForm(forms.Form):
    
    date_iron_started = forms.CharField(
        label="Date iron started", required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    date_iron_completed = forms.CharField(label="Completed", required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    form_type = forms.CharField(widget=forms.HiddenInput(attrs={'id': 'id_form_type_iron'}), initial="iron_intake_form")
    
    def __init__(self, chr_repo: ChildHealthRecordRepository, child_health_record_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._ch_repo = chr_repo
        intake_dates = self._ch_repo.fetch_iron_supplement_completion_by_chr_id(child_health_record_id)
        if intake_dates and isinstance(intake_dates, list):
            if intake_dates[0].__len__() > 0:
                if intake_dates[0]['date_started']:
                    self.fields['date_iron_started'].initial = intake_dates[0]['date_started']
                    self.fields['date_iron_started'].widget.attrs['readonly'] = True
                if intake_dates[0]['date_completed']:
                    self.fields['date_iron_completed'].initial = intake_dates[0]['date_completed']
                    self.fields['date_iron_completed'].widget.attrs['readonly'] = True