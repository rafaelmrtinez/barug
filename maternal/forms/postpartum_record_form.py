from django import forms
from django.forms.utils import ErrorDict

import logging

from maternal.forms.maternal_identification_form import add_bootstrap_classes

logger = logging.getLogger(__name__)


class PostpartumRecordForm(forms.Form):
    """Form for inserting a postpartum record (BHW).

    Fields align with repository.insert_postpartum_record_bhw parameters (except added_by/staff_id
    which is taken from session in the view).
    """
    maternal_record_id = forms.IntegerField(widget=forms.HiddenInput())
    date_of_delivery = forms.DateField(required=True, widget=forms.DateInput(attrs={'type': 'date'}))
    time_of_delivery = forms.TimeField(required=True, widget=forms.TimeInput(attrs={'type': 'time'}))
    # Attended by: present as a dropdown of staff (person id -> display name)
    attended_by_id = forms.ChoiceField(required=False, choices=[], label="Attended By")
    # will be populated with choices in __init__; store as ChoiceField for dropdown
    place_of_delivery_id = forms.ChoiceField(required=False, choices=[], label="Place of Delivery")
    outcome = forms.CharField(required=False, max_length=200)
    # Track dates when supplements/anthelminthic were given (optional)
    # Read-only date showing when iron supplementation started (UI only)
    iron_supplementation = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'readonly': 'readonly'})
    )
    vit_a_supplementation = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    mebendazole_given = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    lochial_discharges_baseline = forms.CharField(required=False, max_length=500)
    pads_per_day_baseline = forms.IntegerField(required=False)

    def __init__(self, mhr_id=None, staff_name=None, staff_id=None, role=None, repository=None, ui_only=True, *args, **kwargs):
        """Initialize form defensively.

        This form may be instantiated in two contexts:
        - rendering for templates (repository and initial values provided)
        - API cleaning/validation (no repository; only data cleaning)

        We avoid DB calls or raising in __init__ when inputs are missing. Only
        perform light sanitization and set initial values when provided.
        """
        super().__init__(*args, **kwargs)

        # Add bootstrap classes when rendering; failure here shouldn't break API usage
        try:
            add_bootstrap_classes(self)
        except Exception:
            logger.exception("add_bootstrap_classes failed for PostpartumRecordForm")

        # Mark whether this form is UI-only (presentation) or used for validation.
        # When ui_only is True we avoid performing server-side validation in full_clean.
        self.ui_only = bool(ui_only)

        # Repository optional — only fetch choices when provided
        self._repository = repository
        self._place_of_delivery_choices = []

        if repository is not None and hasattr(repository, 'fetch_all_delivery_plan'):
            try:
                raw = repository.fetch_all_delivery_plan() or []
                normalized = []
                for row in raw:
                    try:
                        pid, name = row
                        normalized.append((str(pid), name))
                    except Exception:
                        logger.debug("Skipping malformed delivery place row: %s", row)
                self._place_of_delivery_choices = normalized
            except Exception:
                logger.exception("Failed to fetch delivery place choices; continuing with empty list")

        # Populate attended_by choices with midwife staff people (person_id, full_name)
        try:
            if repository is not None and hasattr(repository, 'fetch_midwife_staff_people'):
                raw = repository.fetch_midwife_staff_people() or []
                normalized = []
                for row in raw:
                    try:
                        pid, name = row
                        normalized.append((str(pid), name))
                    except Exception:
                        logger.debug("Skipping malformed midwife staff row: %s", row)
                # default first option prompting user to pick
                self.fields['attended_by_id'].choices = [('', 'Select attended by')] + normalized
        except Exception:
            logger.exception("Failed to set attended_by choices; continuing with empty list")

        # Assign choices (safe if empty)
        try:
            self.fields['place_of_delivery_id'].choices = [('', 'Select place of delivery')] + self._place_of_delivery_choices
        except Exception:
            logger.debug("place_of_delivery_id field missing or failed to set choices")

        # If this form is used only for UI presentation, relax all field requirements
        # and clear field validators so the form won't raise validation errors if
        # accidentally used to clean incoming data.
        if self.ui_only:
            for fname, field in self.fields.items():
                try:
                    field.required = False
                    # clear validators to avoid type/coercion validation during cleaning
                    field.validators = []
                except Exception:
                    logger.debug("Failed to relax field %s; continuing", fname)

        # Set initial values only when explicitly provided
        if mhr_id is not None:
            try:
                self.fields['maternal_record_id'].initial = mhr_id
            except Exception:
                logger.debug("maternal_record_id field missing; skipping initial assignment")

        # Populate iron start/end initial values from micronutrients when available
        try:
            self.iron_intake_incomplete = False
            self.iron_start_date = None
            self.iron_end_date = None
            if repository is not None and hasattr(repository, 'fetch_multiple_micro_nutrients_by_mhr_id') and mhr_id is not None:
                rows = repository.fetch_multiple_micro_nutrients_by_mhr_id(mhr_id) or []
                # rows are dicts with keys iron_start_date and iron_end_date (may be None)
                for r in rows:
                    try:
                        start = r.get('iron_start_date')
                        end = r.get('iron_end_date')
                        if self.iron_start_date is None and start:
                            self.iron_start_date = start
                        if self.iron_end_date is None and end:
                            self.iron_end_date = end
                        # stop early if we have both
                        if self.iron_start_date and self.iron_end_date:
                            break
                    except Exception:
                        continue

                # Rule: do not display a start value if an end exists but start missing
                if self.iron_end_date and not self.iron_start_date:
                    # leave initial empty and do not mark incomplete (no start)
                    self.iron_start_date = None
                else:
                    # if start exists and end missing => intake incomplete
                    if self.iron_start_date and not self.iron_end_date:
                        self.iron_intake_incomplete = True

                if self.iron_start_date:
                    try:
                        self.fields['iron_supplementation'].initial = self.iron_start_date
                    except Exception:
                        logger.debug("Failed to set iron_supplementation initial value")
        except Exception:
            logger.exception("Failed to fetch micronutrients for postpartum form; continuing without defaults")

        if staff_id is not None:
            try:
                # staff_id may be numeric; our choices are strings
                self.fields['attended_by_id'].initial = str(staff_id)
            except Exception:
                logger.debug("attended_by_id field missing; skipping initial assignment")

    def full_clean(self):
        """Override full_clean to skip validation when this form is UI-only.

        When ui_only is True we populate cleaned_data with raw input (or initial
        values) and set _errors to an empty ErrorDict so callers like is_valid()
        will not raise validation errors. This keeps the form usable purely for
        presentation in templates.
        """
        if getattr(self, 'ui_only', False):
            # populate cleaned_data with raw values (no type coercion / validation)
            self._errors = ErrorDict()
            self.cleaned_data = {}
            data = getattr(self, 'data', None)
            if data:
                # data is typically a QueryDict
                for name in self.fields:
                    try:
                        # prefer posted value; fallback to initial
                        val = data.get(name)
                        if val is None:
                            self.cleaned_data[name] = self.fields[name].initial if self.fields[name].initial is not None else None
                        else:
                            self.cleaned_data[name] = val
                    except Exception:
                        self.cleaned_data[name] = None
            else:
                for name, field in self.fields.items():
                    self.cleaned_data[name] = field.initial if field.initial is not None else None
            return

        return super().full_clean()