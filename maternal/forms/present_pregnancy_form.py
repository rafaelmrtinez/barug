from django import forms

import logging

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.repository import MaternalHealthRecordRepository

logger = logging.getLogger(__name__)

# simple yes/no choices (use string values so HTML option values are explicit)
YES_NO_CHOICES = (("1", "Yes"), ("0", "No"))


class PresentPregnancyForm(forms.Form):
    # Present pregnancy
    gravida = forms.IntegerField(
        required=False,
        min_value=0,
        error_messages={
            'invalid': 'Please enter a whole number for gravida.',
            'min_value': 'Gravida cannot be negative.'
        }
    )
    para = forms.IntegerField(
        required=False,
        min_value=0,
        error_messages={
            'invalid': 'Please enter a whole number for para.',
            'min_value': 'Para cannot be negative.'
        }
    )

    # fullterm / preterm are boolean-like choices: Yes / No.
    # Use TypedChoiceField with a coerce function that maps the posted string
    # to True/False and returns None when nothing is selected.
    # Add placeholder option (empty string) so the dropdown displays a prompt.
    FULLTERM_CHOICES = [('', 'Select Fullterm')] + list(YES_NO_CHOICES)
    PRETERM_CHOICES = [('', 'Select Preterm')] + list(YES_NO_CHOICES)

    fullterm = forms.TypedChoiceField(
        choices=FULLTERM_CHOICES,
        coerce=lambda x: True if x == "1" else (False if x == "0" else None),
        required=True,
        empty_value=None,
        label="Fullterm",
        error_messages={'required': 'Please select whether the pregnancy is fullterm.'}
    )

    preterm = forms.TypedChoiceField(
        choices=PRETERM_CHOICES,
        coerce=lambda x: True if x == "1" else (False if x == "0" else None),
        required=True,
        empty_value=None,
        label="Preterm",
        error_messages={'required': 'Please select whether the pregnancy is preterm.'}
    )

    lmp = forms.DateField(required=True, widget=forms.DateInput(
        attrs={'type': 'date'}), label="LMP")
    edc = forms.DateField(required=True, widget=forms.DateInput(
        attrs={'type': 'date'}), label="EDC")
    
    form_type = forms.CharField(widget=forms.HiddenInput(attrs={'id': 'present_pregnancy_form'}), initial="present_pregnancy_form")

    def __init__(self, mhr_repo: MaternalHealthRecordRepository, mhr_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        # Populate initial values from repository (if available).
        self._mhr_repo = mhr_repo
        self._existing_data = self._mhr_repo.fetch_latest_present_pregnancy_by_mhr_id(mhr_id)
        # If existing data is present, set initial values and disable inputs to prevent re-entry
        if self._existing_data and isinstance(self._existing_data, dict):
            # map repo keys to form fields
            self.fields['gravida'].initial = self._existing_data.get('gravida')
            self.fields['para'].initial = self._existing_data.get('para')
            # existing stored values for booleans may be true/false; convert to '1'/'0' for choice fields
            if self._existing_data.get('is_fullterm') is not None:
                self.fields['fullterm'].initial = '1' if self._existing_data.get('is_fullterm') else '0'
            if self._existing_data.get('is_preterm') is not None:
                self.fields['preterm'].initial = '1' if self._existing_data.get('is_preterm') else '0'
            self.fields['lmp'].initial = self._existing_data.get('lmp')
            self.fields['edc'].initial = self._existing_data.get('edc')
            # disable fields in UI to signal they are read-only
            for fname in ('gravida', 'para', 'fullterm', 'preterm', 'lmp', 'edc'):
                if fname in self.fields:
                    self.fields[fname].widget.attrs['readonly'] = True
                    # for select fields, also set disabled attribute
                    # self.fields[fname].widget.attrs['disabled'] = True
        else:
            # No existing data
            pass
            
    def clean(self):
        cleaned_data = super().clean()
        # If existing data present, prevent creating a new entry.
        # Note: when fields are disabled in the HTML they are not included in POST data,
        # so checking cleaned_data for submitted values will be unreliable. Instead,
        # if an existing record is present and the form is bound (i.e. the user
        # submitted the form), block the create and instruct the user to edit.
        print(f"Existing data: {self._existing_data}")
        if getattr(self, '_existing_data', None) and isinstance(self._existing_data, dict):
            print(f"Form is bound: {self.is_bound}")
            if self.is_bound:
                self.add_error(None,
                    "A present pregnancy record already exists for this patient. To change values, please edit the existing record or contact your administrator."
                )
                return cleaned_data

        # Validate fullterm/preterm selection: prevent placeholder values (empty -> None)
        if cleaned_data.get('fullterm') is None:
            self.add_error('fullterm', 'Please select Fullterm (Yes or No).')

        if cleaned_data.get('preterm') is None:
            self.add_error('preterm', 'Please select Preterm (Yes or No).')

        # Validate LMP and EDC logic: LMP must be on or before EDC
        lmp = cleaned_data.get('lmp')
        edc = cleaned_data.get('edc')
        if lmp and edc:
            if lmp > edc:
                self.add_error('edc', 'EDC cannot be earlier than LMP. Please correct the dates.')

        # Ensure gravida/para are non-negative integers (field validators handle format)
        gravida = cleaned_data.get('gravida')
        para = cleaned_data.get('para')
        if gravida is not None and gravida < 0:
            self.add_error('gravida', 'Gravida cannot be negative.')
        if para is not None and para < 0:
            self.add_error('para', 'Para cannot be negative.')

        return cleaned_data


