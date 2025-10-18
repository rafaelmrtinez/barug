from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes

class ChildVisitForm(forms.Form):
    date = forms.DateField(
        label="Date", 
        required=False, 
        widget=forms.DateInput(attrs={'type': 'date'}),
        error_messages={'required': 'Please provide the date of visit.'}
    )
    age = forms.CharField(label="Age", required=False, error_messages={'required': 'Please provide the age.'})
    weight = forms.DecimalField(
        label="Weight", required=False, max_digits=5, decimal_places=2, error_messages={'required': 'Please provide the weight.'})
    temp = forms.DecimalField(
        label="Temp.", required=False, max_digits=4, decimal_places=1, error_messages={'required': 'Please provide the temperature.'})
    height = forms.DecimalField(
        label="Height", required=False, max_digits=5, decimal_places=2, error_messages={'required': 'Please provide the height.'})
    findings = forms.CharField(label="Findings", required=False)
    notes = forms.CharField(label="Notes", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
