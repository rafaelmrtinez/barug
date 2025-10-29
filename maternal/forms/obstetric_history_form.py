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
        
    def clean(self):
        cleaned_data = super().clean()

        # If an obstetric history already exists for this maternal health record,
        # prevent re-entry and provide a clear, user-friendly message.
        # This server-side check complements the UI-level readonly/disabled controls.
        if self._existing_data and isinstance(self._existing_data, dict):
            # If the user submitted any of the main fields, treat this as an attempt
            # to re-enter an already-saved obstetric history and block it.
            submitted_fields = [
                cleaned_data.get('children_born_alive'),
                cleaned_data.get('living_children'),
                cleaned_data.get('abortions'),
                cleaned_data.get('stillbirths'),
                cleaned_data.get('history_large_babies'),
            ]

            if any(value is not None and value != '' for value in submitted_fields):
                # Add a non-field error so it appears at the top of the form
                # and is clearly visible to the user.
                # self.add_error(
                #     None,
                #     "An obstetric history for this record already exists. "
                #     "To change those values, please open the existing record and use the 'Edit' action or contact your administrator."
                # )
                self.add_error(
                    None,
                    "An obstetric history for this record already exists. ")

                # Stop further validation since duplicate entry is not allowed
                return cleaned_data

        # Helpful cross-field validations with clear error messages
        children_born_alive = cleaned_data.get('children_born_alive')
        living_children = cleaned_data.get('living_children')
        abortions = cleaned_data.get('abortions')
        stillbirths = cleaned_data.get('stillbirths')
        history_large_babies = cleaned_data.get('history_large_babies')

        # living_children should not exceed children_born_alive
        if children_born_alive is not None and living_children is not None:
            try:
                if living_children > children_born_alive:
                    self.add_error(
                        'living_children',
                        'Number of living children cannot be greater than number of children born alive.'
                    )
            except TypeError:
                # If values are not integers (should be caught by field validators), skip here
                pass

        # history_large_babies should not exceed children_born_alive
        if children_born_alive is not None and history_large_babies is not None:
            try:
                if history_large_babies > children_born_alive:
                    self.add_error(
                        'history_large_babies',
                        'Number of large babies cannot be greater than number of children born alive.'
                    )
            except TypeError:
                pass

        # Simple sanity check: abortions and stillbirths shouldn't be unreasonably large relative to births
        if children_born_alive is not None:
            # if abortions is provided and seems higher than a reasonable threshold compared to births, warn user
            if abortions is not None and abortions > (children_born_alive + 20):
                self.add_error('abortions', 'Please confirm the number of abortions — it looks unusually high relative to births.')
            if stillbirths is not None and stillbirths > (children_born_alive + 20):
                self.add_error('stillbirths', 'Please confirm the number of stillbirths — it looks unusually high relative to births.')

        return cleaned_data

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