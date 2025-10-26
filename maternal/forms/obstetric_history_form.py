from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.repository import MaternalHealthRecordRepository


class ObstetricHistoryForm(forms.Form):
    # Obstetric history
    children_born_alive = forms.IntegerField(
        required=False, label="No. of children born alive", min_value=0, error_messages={
            'min_value': 'Number of children born alive cannot be negative.',
        })
    living_children = forms.IntegerField(
        required=False, label="No. of living children", min_value=0, error_messages={
            'min_value': 'Number of living children cannot be negative.'
        })
    abortions = forms.IntegerField(required=False, label="No. of abortion", min_value=0, error_messages={
        'min_value': 'Number of abortions cannot be negative.'
    })
    stillbirths = forms.IntegerField(
        required=False, label="No. of still births / fetal death", min_value=0, error_messages={
            'min_value': 'Number of still births / fetal death cannot be negative.'
        })
    history_large_babies = forms.IntegerField(
        required=False, label="History of large babies (≥ 3.6 kg / 8 lbs)", min_value=0, error_messages={
            'min_value': 'Number of large babies cannot be negative.'
        })
    diabetes_history = forms.BooleanField(
        required=False, label="Diabetes (history)")
    form_type = forms.CharField(
        widget=forms.HiddenInput(attrs={'id': 'obstetric_history_form'}), initial="obstetric_history_form"
    )
    
    def __init__(self, maternal_repository: MaternalHealthRecordRepository, mhr_id: int | None,  *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._maternal_repository = maternal_repository
        
        # render ui if data exists during database fetch
        existing_data = self._maternal_repository.fetch_obstetric_history_by_mhr_id(mhr_id)
        
        self._method__ui_display_if_data_exist(existing_data)
        self.__ui_access_policy()

    def _method__ui_display_if_data_exist(self, existing_data):
        if existing_data and isinstance(existing_data, dict):
            self.fields['children_born_alive'].initial = existing_data.get('num_children_born_alive', 'N/A')
            self.fields['living_children'].initial = existing_data.get('num_children_living', 'N/A')
            self.fields['abortions'].initial = existing_data.get('num_abortion', 'N/A')
            self.fields['stillbirths'].initial = existing_data.get('num_stillbirth_or_fetal_death', 'N/A')
            self.fields['history_large_babies'].initial = existing_data.get('num_large_babies', 'N/A')
            if existing_data.get('has_diabetes', None):
                self.fields['diabetes_history'].initial = True

    def __ui_access_policy(self):
        if self.fields['children_born_alive'].initial:
            self.fields['children_born_alive'].widget.attrs['readonly'] = True
        if self.fields['living_children'].initial:
            self.fields['living_children'].widget.attrs['readonly'] = True
        if self.fields['abortions'].initial:
            self.fields['abortions'].widget.attrs['readonly'] = True
        if self.fields['stillbirths'].initial:
            self.fields['stillbirths'].widget.attrs['readonly'] = True
        if self.fields['history_large_babies'].initial:
            self.fields['history_large_babies'].widget.attrs['readonly'] = True
        if self.fields['diabetes_history'].initial:
            self.fields['diabetes_history'].widget.attrs['disabled'] = True