from datetime import datetime
from django import forms
from barug.utility.custom_date_time_util import DateAndTimeUtility
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
        print(f"Iron intake existing data: {intake_dates}")
        self.__ui_date_readonly_policy(intake_dates)
        
    def clean(self):
        cleaned_data = super().clean()

        date_started = cleaned_data.get("date_iron_started")
        date_completed = cleaned_data.get("date_iron_completed")

        # Get Philippine date (timezone-aware)
        today_str = DateAndTimeUtility.get_current_date()
        today = datetime.strptime(today_str, "%Y-%m-%d").date()
        started = DateAndTimeUtility.parse_date(date_started)
        completed = DateAndTimeUtility.parse_date(date_completed)

        # --- Validation rules ---
        self.__date_input_policy(today, started, completed)

        return cleaned_data

    def __date_input_policy(self, today, started, completed):
        if started and started > today:
            self.add_error("date_iron_started", "Date started cannot be in the future.")

        if completed and completed > today:
            self.add_error("date_iron_completed", "Completion date cannot be in the future.")

        if started and completed and completed < started:
            self.add_error("date_iron_completed", "Completion date cannot be before start date.")

    def __ui_date_readonly_policy(self, intake_dates):
        if intake_dates and isinstance(intake_dates, list):
            if intake_dates[0].__len__() > 0:
                if intake_dates[0]['date_started']:
                    self.fields['date_iron_started'].initial = intake_dates[0]['date_started']
                    self.fields['date_iron_started'].widget.attrs['readonly'] = True
                if intake_dates[0]['date_completed']:
                    self.fields['date_iron_completed'].initial = intake_dates[0]['date_completed']
                    self.fields['date_iron_completed'].widget.attrs['readonly'] = True
        else:
            if not self.fields['date_iron_started'].initial:
                self.fields['date_iron_completed'].widget.attrs['readonly'] = True   
            