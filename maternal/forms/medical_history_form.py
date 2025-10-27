from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.forms.form_utils import FormUtils
from maternal.repository import MaternalHealthRecordRepository


class MedicalHistoryForm(forms.Form):
    ## Medical history
    previous_illness = forms.CharField(
        required=True,
        label="Previous illness",
        error_messages={
            'required': "Please provide previous illnesses or enter 'N/A' if none.",
            'invalid': 'Please enter valid text for previous illnesses.'
        })
    previous_hospitalization = forms.CharField(
        required=True,
        label="Previous hospitalization",
        error_messages={
            'required': "Please provide previous hospitalizations or enter 'N/A' if none.",
            'invalid': 'Please enter valid text for previous hospitalizations.'
        })
    previous_preg_complications = forms.CharField(
        required=True,
        label="Previous pregnancy complications",
        error_messages={
            'required': "Please provide previous pregnancy complications or enter 'N/A' if none.",
            'invalid': 'Please enter valid text for previous pregnancy complications.'
        })
    form_type = forms.CharField(
        widget=forms.HiddenInput(attrs={'id': 'medical_history_form'}), initial="medical_history_form"
    )

    def __init__(self, maternal_repository: MaternalHealthRecordRepository, mhr_id: int | None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._maternal_repository = maternal_repository
        # store existing data for potential server-side checks (read-only enforcement etc.)
        self._existing_data = self._maternal_repository.fetch_medical_history_by_mhr_id(mhr_id) if mhr_id else None
        self.__ui_default_display(self._existing_data)
        self.__ui_display_policy()

    def clean(self):
        """
        Normalize and validate text fields. If the user truly has nothing to report,
        require them to enter 'N/A' (case-insensitive). Strip leading/trailing whitespace
        and normalize 'n/a' -> 'N/A'. Provide concise, professional messages.
        """
        cleaned_data = super().clean()

        text_fields = [
            'previous_illness',
            'previous_hospitalization',
            'previous_preg_complications',
        ]

        # If an existing medical history exists for this maternal health record,
        # prevent re-entry and provide a clear, user-friendly message.
        if getattr(self, '_existing_data', None) and isinstance(self._existing_data, dict):
            submitted_values = [cleaned_data.get(f) for f in text_fields]
            if any(value is not None and value != '' for value in submitted_values):
                self.add_error(
                    None,
                    "A medical history for this record already exists. "
                    # "To update those details, please open the existing record and use the 'Edit' action or contact your administrator."
                )
                # Stop further validation since duplicate entry is not allowed
                return cleaned_data

        for field_name in text_fields:
            value = cleaned_data.get(field_name)
            label = self.fields[field_name].label or field_name.replace('_', ' ').capitalize()

            if value is None:
                # Let the field-level 'required' message handle missing values
                continue

            normalized, error = FormUtils.sanitize_text(value, label)
            if error:
                self.add_error(field_name, error)
                continue
            # Only update cleaned_data when sanitized successfully
            cleaned_data[field_name] = normalized

        return cleaned_data

    def __ui_display_policy(self):
        if self.fields['previous_illness'].initial:
            self.fields['previous_illness'].widget.attrs['readonly'] = True
        if self.fields['previous_hospitalization'].initial:
            self.fields['previous_hospitalization'].widget.attrs['readonly'] = True
        if self.fields['previous_preg_complications'].initial:
            self.fields['previous_preg_complications'].widget.attrs['readonly'] = True

    def __ui_default_display(self, existing_data):
        if existing_data:
            self.fields['previous_illness'].initial = existing_data.get('previous_illness', '')
            self.fields['previous_hospitalization'].initial = existing_data.get('previous_hospitalization', '')
            self.fields['previous_preg_complications'].initial = existing_data.get('previous_preg_complication', '')