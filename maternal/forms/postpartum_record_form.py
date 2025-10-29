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
    # staff id should not be displayed to the user — keep as hidden input
    attended_by_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    # display staff name and role (read-only)
    attended_by_name = forms.CharField(required=False, max_length=200)
    attended_by_rolename = forms.CharField(required=False, max_length=100)
    # will be populated with choices in __init__; store as ChoiceField for dropdown
    place_of_delivery_id = forms.ChoiceField(required=False, choices=[], label="Place of Delivery")
    outcome = forms.CharField(required=False, max_length=200)
    iron_supplementation = forms.BooleanField(required=False)
    vit_a_supplementation = forms.BooleanField(required=False)
    mebendazole_given = forms.BooleanField(required=False)
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

        if staff_id is not None:
            try:
                self.fields['attended_by_id'].initial = staff_id
            except Exception:
                logger.debug("attended_by_id field missing; skipping initial assignment")

        if staff_name is not None:
            try:
                self.fields['attended_by_name'].initial = staff_name
                self.fields['attended_by_name'].widget.attrs['readonly'] = True
            except Exception:
                logger.debug("attended_by_name field missing; skipping initial assignment")

        if role is not None:
            try:
                self.fields['attended_by_rolename'].initial = role
                self.fields['attended_by_rolename'].widget.attrs['readonly'] = True
            except Exception:
                logger.debug("attended_by_rolename field missing; skipping initial assignment")

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