from django import forms
from child_health.repository import ChildHealthRecordRepository
from maternal.forms.maternal_identification_form import add_bootstrap_classes

class BirthAndSupplentationForm(forms.Form):
    # Immunization fields: these map to a table, so use per field for each dose.
    # child_record_id = forms.IntegerField(widget=forms.HiddenInput())
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
    
    form_type = forms.CharField(widget=forms.HiddenInput(), initial='birth_and_supplementation_form')

    def __init__(self, chr_repo: ChildHealthRecordRepository, child_health_record_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        latest_screening_data = chr_repo.fetch_child_screening_package(child_health_record_id)
        tt_status_mother = chr_repo.fetch_mother_tt_type(child_health_record_id)
        if latest_screening_data:
            """ Assign data accordingly
            
                Result: Latest Screening Data: {
                    'child_record_id': 7, 
                    'date_assessed': datetime.date(2025, 2, 10), 
                    'birth_weight': Decimal('3.20'), 
                    'anemic_2_59_seen_date': None, 
                    'anemic_2_59_given_iron_date': None, 
                    'seen_2_6_mos_date': None, 
                    'given_2_6_mos_date': None, 
                    'iron_date_started': datetime.date(2025, 3, 1), 
                    'iron_date_completed': datetime.date(2025, 4, 1), 
                    'vit_a_given_1': None, 
                    'vit_a_given_2': None, 
                    'vit_a_given_3': None}
                    
                If data is None in DB, assign False to BooleanFields to avoid 'None' display.
            """
            print("Latest Screening Data:", latest_screening_data)
            # self.fields['child_record_id'].initial = latest_screening_data['child_record_id']
            self.fields['data_assessed'].initial = latest_screening_data['date_assessed'] or ''
            self.fields['birth_weight'].initial = latest_screening_data['birth_weight'] or ''
            self.fields['anemia_2_59_seen'].initial = latest_screening_data['anemic_2_59_seen_date'] or ''
            self.fields['anemia_2_59_given_iron'].initial = latest_screening_data['anemic_2_59_given_iron_date'] or ''
            self.fields['birth_wt_seen'].initial = latest_screening_data['seen_2_6_mos_date'] or ''
            self.fields['birth_wt_given_iron'].initial = latest_screening_data['given_2_6_mos_date'] or ''
        
        print("TT Status Mother Data:", tt_status_mother)
        if tt_status_mother:
            if isinstance(tt_status_mother, list) and len(tt_status_mother) > 0:
                if tt_status_mother[0].get('tt_type_name') and tt_status_mother[0].get('tt_type_id'):
                    self.fields['tt_status_mother'].initial = tt_status_mother[0].get('tt_type_name', '')