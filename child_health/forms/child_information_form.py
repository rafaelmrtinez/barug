from django import forms

from child_health.repository import ChildHealthRecordRepository
from maternal.constants import PLACE_OF_DELIVERY_CHOICES, SEX_CHOICES
from maternal.forms.maternal_identification_form import add_bootstrap_classes

class ChildInformationForm(forms.Form):
    # make fields non fillable
    child_health_record_id = forms.IntegerField(widget=forms.HiddenInput(), required=False, error_messages={'required': 'Child Health Record ID is required.'})
    family_no = forms.CharField(
        label="Family No.", required=False, error_messages={'required': 'Family No. is required.'})
    ufc_no = forms.CharField(label="UFC No.", required=False, error_messages={'required': 'UFC No. is required.'})
    name = forms.CharField(label="Name", required=True, error_messages={'required': 'Name is required.'})
    sex = forms.ChoiceField(
        label="Sex", choices=SEX_CHOICES, required=False, error_messages={'required': 'Sex is required.'})
    birth_order = forms.IntegerField(
        label="Birth Order", required=False, min_value=1, error_messages={'required': 'Birth Order is required.'})
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

    def __init__(self, chr_repo: ChildHealthRecordRepository | None, child_health_record_id: int | None, role: str | None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._chr_repo = chr_repo
        self._child_health_record_id = child_health_record_id
        
        if role:
            if role == 'barangay health worker':
                self.__health_worker_policy(role)
            elif role == 'midwife':
                self.__display_child_data()
                self.display_info_if_exist()
                for field in self.fields.values():
                    field.disabled = True

    def display_info_if_exist(self):
        fetch_data = self._chr_repo.fetch_child_health_record_info_by_chr_id(self._child_health_record_id)
        if fetch_data and isinstance(fetch_data, list) and len(fetch_data) > 0:
            self.fields['name'].initial = fetch_data[0].get('child_full_name', '')
            self.fields['ufc_no'].initial = fetch_data[0].get('ufc_num', '')
            self.fields['family_no'].initial = fetch_data[0].get('family_num', '')
            self.fields['date_of_birth'].initial = fetch_data[0].get('date_of_birth', '')
            self.fields['place_of_delivery'].initial = fetch_data[0].get('place_of_delivery', '')
            self.fields['mother'].initial = fetch_data[0].get('mother_full_name', '')
            self.fields['father'].initial = fetch_data[0].get('father_full_name', '')
            self.fields['mother_age'].initial = fetch_data[0].get('mothers_age', '')
            self.fields['father_age'].initial = fetch_data[0].get('fathers_age', '')
            self.fields['address'].initial = fetch_data[0].get('child_complete_address', '')
            self.fields['birth_order'].initial = fetch_data[0].get('birth_order', '')
            self.fields['mother_occupation'].initial = fetch_data[0].get('mother_occupation', '')
            self.fields['father_occupation'].initial = fetch_data[0].get('fathers_occupation', '')

    def __health_worker_policy(self, role):        
            """ 
                for barangay health workers, Family No, UFC No., Name, Sex, Birth Order, Date of Birth, Place of Delivery
                Mother Name, Age, Mother, and Address is required
            """
            self.fields['place_of_delivery'].widget.attrs['readonly'] = True
            
            # readonyl fields
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
            
            self.fields['family_no'].error_messages = {'required': 'Family No. is required.'}
            self.fields['ufc_no'].error_messages = {'required': 'UFC No. is required.'}
            self.fields['name'].error_messages = {'required': 'Name is required.'}
            self.fields['sex'].error_messages = {'required': 'Sex is required.'}
            self.fields['birth_order'].error_messages = {'required': 'Birth Order is required.'}
            self.fields['date_of_birth'].error_messages = {'required': 'Date of Birth is required.'}
            self.fields['place_of_delivery'].error_messages = {'required': 'Place of Delivery is required.'}
            self.fields['mother'].error_messages = {'required': 'Mother Name is required.'}
            self.fields['mother_age'].error_messages = {'required': 'Mother Age is required.'}
            self.fields['address'].error_messages = {'required': 'Address is required.'}

    def __display_child_data(self):
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
            