from django import forms
from child_health.repository import ChildHealthRecordRepository
from maternal.forms.maternal_identification_form import add_bootstrap_classes

class BirthAndSupplentationForm(forms.Form):
    # Immunization fields: these map to a table, so use per field for each dose.
    # child_protected_at_birth = forms.CharField(label="Child protected at birth", required=False)
    data_assessed = forms.CharField(
        label="Date assessed", 
        required=False, 
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control"}), 
        error_messages={'required': 'Please provide the date assessed.'})
    tt_status_mother = forms.CharField(label="Tetanus Toxoid (TT) Status", required=False, disabled=True)
    anemia_2_59_seen = forms.CharField(
        label="Anemic children 2-59 mos. Seen", required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    anemia_2_59_given_iron = forms.CharField(
        label="Anemic children 2-59 mos. Given iron", required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    birth_weight = forms.DecimalField(
        label="Birth weight", 
        required=False, 
        max_digits=5, 
        decimal_places=2,
        error_messages={'required': 'Please provide the birth weight.'})
    low_birth_weight = forms.BooleanField(
        label="If low birth weight", required=False)
    birth_wt_seen = forms.CharField(label="2-6 mos. Seen", required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    birth_wt_given_iron = forms.CharField(label="2-6 mos. Given iron", required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))

    form_type = forms.CharField(widget=forms.HiddenInput(attrs={'id': 'id_form_type_bs'}), initial='birth_and_supplementation_form')

    def __init__(self, chr_repo: ChildHealthRecordRepository, child_health_record_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)

        # --- Step 1: Fetch Data ---
        latest_screening_data = chr_repo.fetch_child_screening_package(child_health_record_id)
        tt_status_mother = chr_repo.fetch_mother_tt_type(child_health_record_id)

        # --- Step 2: Validate and Normalize Data ---
        def safe_date(value):
            """Return None instead of empty string."""
            return value or None

        if latest_screening_data:
            # Clean values first
            cleaned_data = {
                'date_assessed': safe_date(latest_screening_data.get('date_assessed')),
                'birth_weight': latest_screening_data.get('birth_weight') or '',
                'anemic_2_59_seen_date': safe_date(latest_screening_data.get('anemic_2_59_seen_date')),
                'seen_2_6_mos_date': safe_date(latest_screening_data.get('seen_2_6_mos_date')),
                'given_2_6_mos_date': safe_date(latest_screening_data.get('given_2_6_mos_date')),
                'anemic_2_59_given_iron_date': safe_date(latest_screening_data.get('anemic_2_59_given_iron_date')),
            }

            # --- Step 3: Initialize Fields ---
            self.fields['data_assessed'].initial = cleaned_data['date_assessed']
            self.fields['birth_weight'].initial = cleaned_data['birth_weight']
            self.fields['anemia_2_59_seen'].initial = cleaned_data['anemic_2_59_seen_date']
            self.fields['birth_wt_seen'].initial = cleaned_data['seen_2_6_mos_date']
            self.fields['birth_wt_given_iron'].initial = cleaned_data['given_2_6_mos_date']
            self.fields['anemia_2_59_given_iron'].initial = cleaned_data['anemic_2_59_given_iron_date']

            # --- Step 4: Apply Field Restrictions ---
            if not cleaned_data['anemic_2_59_seen_date']:
                self.fields['anemia_2_59_given_iron'].widget.attrs['readonly'] = True

            if not cleaned_data['seen_2_6_mos_date']:
                self.fields['birth_wt_given_iron'].widget.attrs['readonly'] = True

        # --- Step 5: Initialize TT Status ---
        if tt_status_mother and isinstance(tt_status_mother, list) and tt_status_mother:
            first_tt = tt_status_mother[0]
            tt_name = first_tt.get('tt_type_name')
            tt_id = first_tt.get('tt_type_id')
            if tt_name and tt_id:
                self.fields['tt_status_mother'].initial = tt_name
