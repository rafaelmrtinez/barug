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
        
    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        # Normalize stages from repository
        stages = self._existing_stages or []
        if stages and isinstance(stages[0], dict):
            stages = {s.get("vitamin_a_stage_id") for s in stages if s.get("vitamin_a_stage_id")}
        else:
            stages = set(stages)
        max_existing_stage = max(stages) if stages else 0
        # Incoming request — form checkboxes
        requested = {
            1: cleaned_data.get("vit_a_1"),
            2: cleaned_data.get("vit_a_2"),
            3: cleaned_data.get("vit_a_3"),
        }
        # Determine which stages user wants to give now (True)
        requested_stages = [stage for stage, checked in requested.items() if checked]
        if not requested_stages:
            cleaned_data["vit_a_stage"] = None
            return cleaned_data
        latest_requested_stage = max(requested_stages)
        # Rule 1: Check that all preceding stages exist or are selected
        for stage in range(1, latest_requested_stage):
            if stage not in stages and not requested.get(stage):
                self.add_error(
                    f"vit_a_{latest_requested_stage}",
                    f"Cannot give stage {latest_requested_stage} before completing stage {stage}."
                )
        # Rule 2: Prevent re-adding an already existing stage
        if latest_requested_stage in stages:
            self.add_error(
                f"vit_a_{latest_requested_stage}",
                f"Vitamin A stage {latest_requested_stage} already exists in the database."
            )
        cleaned_data["vit_a_stage"] = latest_requested_stage
        return cleaned_data
