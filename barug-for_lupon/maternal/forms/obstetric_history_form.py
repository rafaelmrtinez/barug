from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository


class ObstetricHistoryForm(forms.Form):
    # Obstetric history
    children_born_alive = forms.IntegerField(
        required=True,
        label="No. of children born alive",
        min_value=0,
        error_messages={
            'required': 'Please enter the number of children born alive.',
            'invalid': 'Please enter a whole number for children born alive.',
            'min_value': 'Number of children born alive cannot be negative.',
        })
    living_children = forms.IntegerField(
        required=True,
        label="No. of living children",
        min_value=0,
        error_messages={
            'required': 'Please enter the number of living children.',
            'invalid': 'Please enter a whole number for living children.',
            'min_value': 'Number of living children cannot be negative.'
        })
    abortions = forms.IntegerField(required=True, label="No. of abortion", min_value=0, error_messages={
        'required': 'Please enter the number of abortions (enter 0 if none).',
        'invalid': 'Please enter a whole number for abortions.',
        'min_value': 'Number of abortions cannot be negative.'
    })
    stillbirths = forms.IntegerField(
        required=True,
        label="No. of still births / fetal death",
        min_value=0,
        error_messages={
            'required': 'Please enter the number of stillbirths / fetal deaths (enter 0 if none).',
            'invalid': 'Please enter a whole number for stillbirths / fetal death.',
            'min_value': 'Number of still births / fetal death cannot be negative.'
        })
    history_large_babies = forms.IntegerField(
        required=True,
        label="History of large babies (≥ 3.6 kg / 8 lbs)",
        min_value=0,
        error_messages={
            'required': 'Please enter how many large babies (enter 0 if none).',
            'invalid': 'Please enter a whole number for history of large babies.',
            'min_value': 'Number of large babies cannot be negative.'
        })
    diabetes_history = forms.BooleanField(
        required=False, label="Diabetes (history)", error_messages={
            'invalid': 'Invalid value for diabetes history.'
        })
    form_type = forms.CharField(
        widget=forms.HiddenInput(attrs={'id': 'obstetric_history_form'}), initial="obstetric_history_form"
    )
    
    def __init__(self, maternal_repository: MaternalHealthRecordRepository, mhr_id: int | None,  *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._maternal_repository = maternal_repository
        
        # render ui if data exists during database fetch
        self._existing_data = self._maternal_repository.fetch_obstetric_history_by_mhr_id(mhr_id)

        self._method__ui_display_if_data_exist(self._existing_data)
        self.__ui_access_policy()

    def _method__ui_display_if_data_exist(self, existing_data):
        if existing_data and isinstance(existing_data, dict):
            def _coerce(v):
                if v is None:
                    return None
                # coerce numeric strings to int
                try:
                    return int(v)
                except Exception:
                    # coerce common truthy strings to bool
                    if isinstance(v, str) and v.lower() in ('t', 'true', '1'):
                        return True
                    return v

            # Repository returns keys matching column names; map them here.
            self.fields['children_born_alive'].initial = _coerce(existing_data.get('num_children_born_alive'))
            self.fields['living_children'].initial = _coerce(existing_data.get('num_children_living'))
            self.fields['abortions'].initial = _coerce(existing_data.get('num_abortion'))
            # repository uses `num_stillbirth`; map to the form field
            self.fields['stillbirths'].initial = _coerce(existing_data.get('num_stillbirth'))
            self.fields['history_large_babies'].initial = _coerce(existing_data.get('num_large_babies'))
            if _coerce(existing_data.get('has_diabetes')):
                self.fields['diabetes_history'].initial = True

    def __ui_access_policy(self):
        # If initial is set (including zero-values), make the field readonly.
        for fname in ('children_born_alive', 'living_children', 'abortions', 'stillbirths', 'history_large_babies'):
            init = self.fields[fname].initial
            if init is not None:
                self.fields[fname].widget.attrs['readonly'] = True
        # For boolean fields, disable if initial is truthy
        if self.fields['diabetes_history'].initial is not None:
            # Use disabled attribute for checkbox
            self.fields['diabetes_history'].widget.attrs['disabled'] = True