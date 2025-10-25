from django import forms

import logging

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.repository import MaternalHealthRecordRepository

logger = logging.getLogger(__name__)

# simple yes/no choices (use string values so HTML option values are explicit)
YES_NO_CHOICES = (("1", "Yes"), ("0", "No"))


class PresentPregnancyForm(forms.Form):
    # Present pregnancy
    gravida = forms.IntegerField(required=False)
    para = forms.IntegerField(required=False)

    # fullterm / preterm are boolean-like choices: Yes / No.
    # Use TypedChoiceField with a coerce function that maps the posted string
    # to True/False and returns None when nothing is selected.
    fullterm = forms.TypedChoiceField(
        choices=YES_NO_CHOICES,
        coerce=lambda x: True if x == "1" else (False if x == "0" else None),
        required=False,
        empty_value=None,
        label="Fullterm",
    )

    preterm = forms.TypedChoiceField(
        choices=YES_NO_CHOICES,
        coerce=lambda x: True if x == "1" else (False if x == "0" else None),
        required=False,
        empty_value=None,
        label="Preterm",
    )

    lmp = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="LMP")
    edc = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="EDC")
    
    form_type = forms.CharField(widget=forms.HiddenInput(attrs={'id': 'present_pregnancy_form'}), initial="present_pregnancy_form")

    def __init__(self, mhr_repo: MaternalHealthRecordRepository, mhr_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        # Populate initial values from repository (if available).
        present_pregnancy_data = self._fetch_existing(mhr_repo, mhr_id)
        if present_pregnancy_data:
            # mark form as populated so callers can prevent re-insert
            self._populate_from_existing(present_pregnancy_data)
            # Wire up UI-level readonly behavior separately so callers
            # can choose to skip or replace it later.
            self._apply_readonly(['gravida', 'para', 'fullterm', 'preterm', 'lmp', 'edc'])
        else:
            self.populated = False
            
    def clean(self):
        cleaned_data = super().clean()
        # Server-side safeguard: prevent duplicate insert when data already exists.
        self._validate_not_populated()

        logger.debug("PresentPregnancyForm cleaned: %s", {k: v for k, v in cleaned_data.items() if k not in ['lmp', 'edc']})
        return cleaned_data

    def _fetch_existing(self, mhr_repo: MaternalHealthRecordRepository, mhr_id: int):
        """Fetch the latest present pregnancy record for the given maternal
        record id. Return a dict-like object or None. The method swallows
        repository exceptions and returns None to keep form construction
        tolerant to repository failures.
        """
        try:
            return mhr_repo.fetch_latest_present_pregnancy_by_mhr_id(mhr_id)
        except Exception:
            # Be conservative: don't let repo errors break form construction.
            return None

    @staticmethod
    def _bool_to_choice(v):
        """Convert boolean/None to the form choice string."""
        if v is True:
            return "1"
        if v is False:
            return "0"
        return None

    def _populate_from_existing(self, data: dict):
        """Populate form initial values from repository data and set
        self.populated = True.
        """
        self.populated = True
        self.fields['gravida'].initial = data.get('gravida')
        self.fields['para'].initial = data.get('para')
        self.fields['fullterm'].initial = self._bool_to_choice(data.get('is_fullterm'))
        self.fields['preterm'].initial = self._bool_to_choice(data.get('is_preterm'))
        self.fields['lmp'].initial = data.get('lmp')
        self.fields['edc'].initial = data.get('edc')

    def _apply_readonly(self, field_names):
        """Disable and mark widgets readonly for the provided field names.
        This can be replaced or skipped by callers to change UI behavior.
        """
        for fname in field_names:
            field = self.fields.get(fname)
            if field is None:
                continue
            # Mark as disabled so the widget renders non-editable in browsers
            field.disabled = True
            # For input-like widgets, also add readonly attr to improve UX
            try:
                widget = field.widget
                if widget is not None:
                    existing = dict(getattr(widget, 'attrs', {}))
                    existing.update({'readonly': 'readonly'})
                    widget.attrs = existing
            except Exception:
                # If a widget doesn't accept attrs, skip it silently.
                pass

    def _validate_not_populated(self):
        """Raise ValidationError when the form was populated from the DB.
        Separated out so callers can override or skip this behavior.
        """
        if getattr(self, 'populated', False):
            raise forms.ValidationError(
                "Present pregnancy data already exists for this maternal record and cannot be inserted again."
            )