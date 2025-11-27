"""Forms for Child Health Record basic information.

This module defines `ChildInformationForm`, a Django `forms.Form` used to
display and (in some cases) restrict editing of basic child health record
information. The form is used by different roles in the application and
adapts its behavior depending on the provided `role` and `is_readonly`
flag.

Key constructor parameters:
 - chr_repo: repository used to fetch child/record data (may be None in tests)
 - child_health_record_id: integer id of the child health record (may be None)
 - role: string role name (e.g. 'midwife' or 'barangay health worker')
 - is_readonly: when True, the form should render fields disabled for editing

This module only adds documentation and clarifying comments — it does not
change runtime behavior.
"""

from django import forms

from src.infra.repositories.child_health_record_repository import ChildHealthRecordRepository
from maternal.constants import PLACE_OF_DELIVERY_CHOICES, SEX_CHOICES
from maternal.forms.maternal_identification_form import add_bootstrap_classes

class ChildInformationForm(forms.Form):
    """Form containing the child's basic information fields.

    The form defines fields that correspond to the child health record's
    basic attributes (family number, UFC number, name, sex, birth order,
    date of birth, parents' names/ages/occupations, address, etc.).

    Role- and readonly-aware behavior:
    - When `role == 'barangay health worker'` and `is_readonly` is False,
      additional server-side UI policies are applied via
      `__health_worker_policy` and then the form fields are rendered as
      read-only by `_readonly_fields` (this preserves the display-only
      behaviour while keeping some UI hints for BHWs).
    - When `role == 'midwife'`, the form is displayed read-only.

    The form expects a `ChildHealthRecordRepository` instance to fetch
    existing data to populate initial field values.
    """
    # make fields non fillable
    child_health_record_id = forms.IntegerField(widget=forms.HiddenInput(), required=False, error_messages={'required': 'Child Health Record ID is required.'})
    family_no = forms.CharField(
        label="Family No.", required=False, error_messages={'required': 'Family No. is required.'})
    ufc_no = forms.CharField(label="UFC No.", required=False, error_messages={'required': 'UFC No. is required.'})
    name = forms.CharField(label="Name", required=True, error_messages={'required': 'Name is required.'})
    sex = forms.ChoiceField(
        label="Sex", choices=SEX_CHOICES, required=False, error_messages={'required': 'Sex is required.'})
    birth_order = forms.IntegerField(
        label="Birth Order", required=True, min_value=1, error_messages={'required': 'Birth Order is required.'})
    date_of_birth = forms.DateField(label="Date of Birth", required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), error_messages={'required': 'Date of Birth is required.'})
    place_of_delivery = forms.ChoiceField(
        label="Place of Delivery",
        choices=PLACE_OF_DELIVERY_CHOICES,
        required=False,
        widget=forms.Select,
        error_messages={'required': 'Place of Delivery is required.'}
    )
    mother = forms.CharField(label="Mother", required=False, error_messages={'required': 'Mother is required.'})
    mother_age = forms.IntegerField(
        label="Age", required=False, min_value=0, error_messages={'required': 'Mother Age is required.'})
    mother_occupation = forms.CharField(
        label="Mother Occupation", required=False, error_messages={'required': 'Mother Occupation is required.'})
    father = forms.CharField(label="Father", required=False,)
    father_age = forms.IntegerField(
        label="Age", required=False, min_value=0,)
    father_occupation = forms.CharField(
        label="Father Occupation", required=False, error_messages={'required': 'Father Occupation is required.'})
    address = forms.CharField(label="Complete Address with landmarks", required=False, widget=forms.Textarea(attrs={'rows': 2}), error_messages={'required': 'Address is required.'})

    def __init__(self, chr_repo: ChildHealthRecordRepository | None, child_health_record_id: int | None, role: str | None, is_readonly: bool | None, *args, **kwargs):
        """Initialize the form.

        Parameters:
        - chr_repo: a ChildHealthRecordRepository used to fetch existing data.
        - child_health_record_id: the id used when fetching record/person data.
        - role: the current user's role name; affects which fields are editable.
        - is_readonly: external flag that may prevent editing even for BHW.

        The form adds Bootstrap classes, stores repository/context, and then
        applies role-specific policies. For BHWs, `__health_worker_policy`
        will adjust required/error messages and field attributes, then
        `_readonly_fields` marks fields disabled for display.
        """
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._chr_repo = chr_repo
        self._child_health_record_id = child_health_record_id
        # Apply role-specific UI policies and display-only behaviour.
        # Apply role-specific UI policies and display-only behaviour.
        # Keep behavior unchanged (BHW and midwife get display-only view),
        # but avoid passing unused parameters into helpers.
        if role:
            if role == 'barangay health worker':
                if not is_readonly:
                    # Apply BHW-specific policy (adjusts required/errors/attrs)
                    self.__health_worker_policy()
                    return
                # After policy adjustments, render fields read-only for display
                self._readonly_fields()
            elif role == 'midwife':
                # Midwives view the form as display-only
                self._readonly_fields()
                    
    def _readonly_fields(self):
        """Populate display data and disable all fields for read-only view.

        This method fills the form with available child data (both from the
        person table via `__display_child_data` and from the record via
        `display_info_if_exist`) and then marks all fields as disabled so
        they render as non-editable in templates.
        """
        # Populate basic child/person information first
        self.__display_child_data()
        # Overlay any record-specific info if present
        self.display_info_if_exist()
        # Disable all fields so the HTML inputs render as read-only
        for field in self.fields.values():
            field.disabled = True
            
    def display_info_if_exist(self):
        """Fetch and populate record-level info when available.

        The repository call may return a list (from a DB fetch); if data
        exists we populate the form's `.initial` values so the template
        renders the record's information.
        """
        # Guard if repository or id not provided (prevent AttributeError)
        if not self._chr_repo or not self._child_health_record_id:
            return

        fetch_data = self._chr_repo.fetch_child_health_record_info_by_chr_id(self._child_health_record_id)
        # Repository typically returns a list; treat any non-empty result as valid
        if fetch_data:
            row = fetch_data[0]
            self.fields['name'].initial = row.get('child_full_name', '')
            self.fields['ufc_no'].initial = row.get('ufc_num', '')
            self.fields['family_no'].initial = row.get('family_num', '')
            self.fields['date_of_birth'].initial = row.get('date_of_birth', '')
            self.fields['place_of_delivery'].initial = row.get('place_of_delivery', '')
            self.fields['mother'].initial = row.get('mother_full_name', '')
            self.fields['father'].initial = row.get('father_full_name', '')
            self.fields['mother_age'].initial = row.get('mothers_age', '')
            self.fields['father_age'].initial = row.get('fathers_age', '')
            self.fields['address'].initial = row.get('child_complete_address', '')
            self.fields['birth_order'].initial = row.get('birth_order', '')
            self.fields['mother_occupation'].initial = row.get('mother_occupation', '')
            self.fields['father_occupation'].initial = row.get('fathers_occupation', '')

    def __health_worker_policy(self):
        """Adjust field attributes and error messages for BHW role.

        This helper configures which fields are read-only at the widget
        attribute level for barangay health workers and adjusts the
        `error_messages` for required fields so form validation and the
        UI provide the expected messages.
        """
        # Mark a subset of widgets readonly (client-side hint)
        self.fields['place_of_delivery'].widget.attrs['readonly'] = True

        # readonly fields (widget-level attribute only)
        self.fields['family_no'].widget.attrs['readonly'] = True
        self.fields['ufc_no'].widget.attrs['readonly'] = True
        self.fields['sex'].widget.attrs['readonly'] = True
        self.fields['date_of_birth'].widget.attrs['readonly'] = True
        self.fields['address'].widget.attrs['readonly'] = True
        self.fields['mother_age'].widget.attrs['readonly'] = True
        self.fields['mother_occupation'].widget.attrs['readonly'] = True
        self.fields['father_age'].widget.attrs['readonly'] = True
        self.fields['father_occupation'].widget.attrs['readonly'] = True
        self.fields["mother"].widget.attrs['readonly'] = True
        self.fields["father"].widget.attrs['readonly'] = True

        # Set helpful required-field messages for the BHW UI in a single pass
        bhw_required_errors = {
            'family_no': 'Family No. is required.',
            'ufc_no': 'UFC No. is required.',
            'name': 'Name is required.',
            'sex': 'Sex is required.',
            'birth_order': 'Birth Order is required.',
            'date_of_birth': 'Date of Birth is required.',
            'place_of_delivery': 'Place of Delivery is required.',
            'mother': 'Mother Name is required.',
            'mother_age': 'Mother Age is required.',
            'address': 'Address is required.',
        }

        for key, msg in bhw_required_errors.items():
            if key in self.fields:
                self.fields[key].error_messages = {'required': msg}

    def __display_child_data(self):
        """Populate basic person-related child information from repository.

        This helper reads basic child/person information (not record-level)
        and populates `.initial` values for the form fields so the
        rendered form displays existing data.
        """
        # Guard if repository or id not provided
        if not self._chr_repo or not self._child_health_record_id:
            return

        child_data = self._chr_repo.fetch_child_basic_information_by_person_id(self._child_health_record_id)
        if child_data:
            self.fields['family_no'].initial = child_data.get('family_num', '')
            self.fields['ufc_no'].initial = child_data.get('ufc_num', '')
            self.fields['name'].initial = child_data.get('child', '')
            self.fields['sex'].initial = child_data.get('sex_name', '')
            self.fields['birth_order'].initial = child_data.get('birth_order', '')
            self.fields['date_of_birth'].initial = child_data.get('date_of_birth', '')
            self.fields['mother'].initial = child_data.get('mother_name', '')
            self.fields['mother_age'].initial = child_data.get('mother_age', '')
            self.fields['mother_occupation'].initial = child_data.get('mother_occupation', '')
            self.fields['father'].initial = child_data.get('father_name', '')
            self.fields['father_age'].initial = child_data.get('father_age', '')
            self.fields['father_occupation'].initial = child_data.get('father_occupation', '')
            self.fields['address'].initial = child_data.get('address', '')
            self.fields['place_of_delivery'].initial = child_data.get('place_of_delivery', '')
            