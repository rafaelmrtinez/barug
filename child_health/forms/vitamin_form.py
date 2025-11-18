from typing import Any
from django import forms
from src.infra.repositories.child_health_record_repository import ChildHealthRecordRepository
from maternal.forms.maternal_identification_form import add_bootstrap_classes

class VitaminForm(forms.Form):
    vit_a_1 = forms.BooleanField(label="Vit. A Given 1", required=False)
    vit_a_2 = forms.BooleanField(label="Vit. A Given 2", required=False)
    vit_a_3 = forms.BooleanField(label="Vit. A Given 3", required=False)

    form_type = forms.CharField(widget=forms.HiddenInput(attrs={'id': 'id_form_type_vit'}), initial="vitamin_form")

    def __init__(self, chr_repo: ChildHealthRecordRepository, child_health_record_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._ch_repo = chr_repo
        self.child_health_record_id = child_health_record_id
        self._existing_stages = self._ch_repo.fetch_vitamin_by_chr_id(self.child_health_record_id) or []
        if self._existing_stages and isinstance(self._existing_stages, list):
            for stage in self._existing_stages:
                if stage['vit_stage_id'] == 1:
                    self.fields['vit_a_1'].initial = True
                    self.fields['vit_a_1'].widget.attrs['readonly'] = True
                elif stage['vit_stage_id'] == 2:
                    self.fields['vit_a_2'].initial = True
                    self.fields['vit_a_2'].widget.attrs['readonly'] = True
                elif stage['vit_stage_id'] == 3:
                    self.fields['vit_a_3'].initial = True
                    self.fields['vit_a_3'].widget.attrs['readonly'] = True
        
