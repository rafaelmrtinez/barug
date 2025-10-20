from django import forms
from child_health.repository import ChildHealthRecordRepository
from maternal.forms.maternal_identification_form import add_bootstrap_classes

class VitaminForm(forms.Form):
    vit_a_1 = forms.BooleanField(label="Vit. A Given 1", required=False)
    vit_a_2 = forms.BooleanField(label="Vit. A Given 2", required=False)
    vit_a_3 = forms.BooleanField(label="Vit. A Given 3", required=False)
    
    def __init__(self, chr_repo: ChildHealthRecordRepository, child_health_record_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        