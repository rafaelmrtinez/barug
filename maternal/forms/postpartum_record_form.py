from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes


class PostpartumRecordForm(forms.Form):
    """Form for inserting a postpartum record (BHW).

    Fields align with repository.insert_postpartum_record_bhw parameters (except added_by/staff_id
    which is taken from session in the view).
    """
    maternal_record_id = forms.IntegerField(widget=forms.HiddenInput())
    date_of_delivery = forms.DateField(required=True, widget=forms.DateInput(attrs={'type': 'date'}))
    time_of_delivery = forms.TimeField(required=True, widget=forms.TimeInput(attrs={'type': 'time'}))
    attended_by_id = forms.IntegerField(required=False)
    attended_by_rolename = forms.CharField(required=False, max_length=100)
    place_of_delivery_id = forms.IntegerField(required=False)
    outcome = forms.CharField(required=False, max_length=200)
    iron_supplementation = forms.BooleanField(required=False)
    vit_a_supplementation = forms.BooleanField(required=False)
    mebendazole_given = forms.BooleanField(required=False)
    lochial_discharges_baseline = forms.CharField(required=False, max_length=500)
    pads_per_day_baseline = forms.IntegerField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)

    def clean_maternal_record_id(self):
        val = self.cleaned_data.get('maternal_record_id')
        try:
            return int(val)
        except (TypeError, ValueError):
            raise forms.ValidationError('Invalid maternal record id')

    def clean_pads_per_day_baseline(self):
        v = self.cleaned_data.get('pads_per_day_baseline')
        if v in (None, ''):
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            raise forms.ValidationError('pads_per_day_baseline must be an integer')
