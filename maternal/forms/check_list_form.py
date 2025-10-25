# forms.py
from django import forms
import re

from maternal.constants import SYMPTOM_CHOICES
from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.repository import MaternalHealthRecordRepository
import logging

logger = logging.getLogger(__name__)

class CheckListForm(forms.Form):
    symptoms = forms.MultipleChoiceField(
        required=False,
        choices=SYMPTOM_CHOICES,
        widget=forms.CheckboxSelectMultiple
    )
    # preeclampsia_flag = forms.BooleanField(required=False, label="Preeclampsia")
    form_type = forms.CharField(initial="check_list_form", widget=forms.HiddenInput(
        attrs={'id': 'check_list_form'}
    ))

    def __init__(self, mhr_repo: MaternalHealthRecordRepository, mhr_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self.mhr_repo = mhr_repo
        self.mhr_id = mhr_id

        # Populate choices from DB (ids & labels) and set initial selected items for this maternal record
        try:
            items = self.mhr_repo.fetch_checklist_items()
            choices = []
            if items:
                # use string IDs for form values (Django form data arrives as strings)
                choices = [(str(r["checklist_item_id"]), r["checklist_name"].title()) for r in items]
                self.fields["symptoms"].choices = choices

            existing = self.mhr_repo.fetch_maternal_checklist_by_mhr_id(self.mhr_id) or []

            # existing is list of rows -> extract the checklist_item_id values and set as strings
            existing_ids = []
            for row in existing:
                # row may already be an int id or a dict containing checklist_item_id
                if isinstance(row, dict):
                    val = row.get("checklist_item_id")
                else:
                    val = row
                if val is not None:
                    existing_ids.append(str(val))

            # set initial selected values as strings to match choices' values
            self.fields["symptoms"].initial = existing_ids
            # also set form-level initial so template helpers/readers see it
            self.initial["symptoms"] = existing_ids

            logger.debug("Checklist choices set: %s, initial: %s", choices if items else None, self.fields["symptoms"].initial)
        except Exception:
            logger.exception("Failed to load checklist items for maternal record %s", self.mhr_id)


    def clean(self):
        cleaned_data = super().clean()
        
        # incoming selected symptoms (as strings)
        incoming = cleaned_data.get("symptoms") or []
        incoming = [str(v) for v in incoming]

        # fetch existing checklist items for this maternal record
        try:
            existing = self.mhr_repo.fetch_maternal_checklist_by_mhr_id(self.mhr_id) or []
        except Exception:
            logger.exception("Failed to fetch existing checklist for mhr %s", self.mhr_id)
            existing = []

        # normalize existing ids to strings (handle list of ints or list of dicts)
        existing_ids = []
        for row in existing:
            if isinstance(row, dict):
                val = row.get("checklist_item_id") or row.get("checklist_item_id")
            else:
                val = row
            if val is not None:
                existing_ids.append(str(val))

        # exclude any incoming items that already exist in DB
        new_items = [item for item in incoming if item not in existing_ids]

        # set cleaned symptoms to only the new (non-existing) items
        cleaned_data["symptoms"] = new_items

        return cleaned_data
