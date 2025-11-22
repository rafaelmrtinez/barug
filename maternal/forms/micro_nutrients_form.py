from django import forms

from maternal.forms.maternal_identification_form import add_bootstrap_classes
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
from src.infra.utilities.custom_date_time_util import DateAndTimeUtility


class MicroNutrientsForm(forms.Form):
    iron_folic_start = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="Iron w/ Folic Acid (start)")
    iron_folic_end = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="Iron w/ Folic Acid (completed)")
    deworming_date = forms.DateField(required=False, widget=forms.DateInput(
        attrs={'type': 'date'}), label="Deworming tab (preferably 3rd trimester) date given")
    form_type = forms.CharField(initial="micro_nutrients_form", widget=forms.HiddenInput(
        attrs={'id': 'micro_nutrients_form'}
    ))

    def __init__(self, mhr_repo: MaternalHealthRecordRepository, mhr_id: int,  *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._mhr_repo = mhr_repo
        self._micronutrients_data = self._mhr_repo.fetch_micronutrients_by_mhr_id(mhr_id)
        print(f'_micronutrients_data: {self._micronutrients_data}')
        # populate form fields only if values are present (not None)
        if self._micronutrients_data:
            iron_start = self._micronutrients_data.get("iron_start_date")
            iron_end = self._micronutrients_data.get("iron_end_date")
            deworm = self._micronutrients_data.get("deworming_date")

            if iron_start is not None:
                self.fields["iron_folic_start"].initial = iron_start
                self.initial["iron_folic_start"] = iron_start
            if iron_end is not None:
                self.fields["iron_folic_end"].initial = iron_end
                self.initial["iron_folic_end"] = iron_end
            if deworm is not None:
                self.fields["deworming_date"].initial = deworm
                self.initial["deworming_date"] = deworm

    def clean(self):
        cleaned_data = super().clean()

        allowed_fields = { 'iron_folic_start', 'deworming_date' }

        # Require at least one of the allowed date fields to be provided.
        # If both are empty, add a friendly field error and return immediately.
        has_allowed = any(cleaned_data.get(f) for f in allowed_fields)
        if not has_allowed:
            self.add_error(None, "Please provide at least one date: either 'Iron w/ Folic Acid (start)' or 'Deworming' before saving. If neither applies, add a brief note explaining why.")
            return cleaned_data

        # Prevent future dates (Philippine timezone) for any provided date fields.
        # Use DateAndTimeUtility.get_current_date() to obtain current PH date.
        try:
            ph_current = DateAndTimeUtility.parse_date(DateAndTimeUtility.get_current_date())
        except Exception:
            ph_current = None

        if ph_current:
            # Determine start/end values: prefer submitted values, fall back to initial
            iron_start_val = cleaned_data.get('iron_folic_start') or self.fields.get('iron_folic_start').initial
            iron_end_val = cleaned_data.get('iron_folic_end')

            # If there is an end date but no start (neither submitted nor initial), require start first
            if iron_end_val and not iron_start_val:
                self.add_error('iron_folic_start', "Please enter the Iron w/ Folic Acid (start) date before providing the completed date.")
                return cleaned_data

            for field_name in ('iron_folic_start', 'iron_folic_end', 'deworming_date'):
                val = cleaned_data.get(field_name)
                if not val:
                    continue
                # val may be a date object or a string; coerce to date
                parsed = None
                if hasattr(val, 'strftime'):
                    try:
                        parsed = val
                    except Exception:
                        parsed = None
                else:
                    parsed = DateAndTimeUtility.parse_date(val)

                if parsed is None:
                    # Invalid date format — add friendly error and stop
                    self.add_error(field_name, f"{self.fields[field_name].label}: the provided date is invalid. Please use YYYY-MM-DD.")
                    return cleaned_data

                # Disallow present or future dates (must be strictly before today's PH date)
                if parsed >= ph_current:
                    self.add_error(field_name, f"{self.fields[field_name].label}: today's date and future dates are not allowed. Please enter a date before {ph_current}.")
                    return cleaned_data

            # If both iron start and end are present, ensure chronological order
            if iron_start_val and iron_end_val:
                # coerce to date objects for comparison (handle initial values which may already be date objects)
                s_parsed = iron_start_val if hasattr(iron_start_val, 'strftime') else DateAndTimeUtility.parse_date(iron_start_val)
                e_parsed = iron_end_val if hasattr(iron_end_val, 'strftime') else DateAndTimeUtility.parse_date(iron_end_val)
                # If end is earlier than start, reject
                if s_parsed and e_parsed and e_parsed < s_parsed:
                    self.add_error('iron_folic_end', "Iron w/ Folic Acid (completed) cannot be earlier than the start date. Please correct the dates.")
                    return cleaned_data
                # Also ensure end is not in the present/future (already checked above), but double-check in case start came from initial
                if e_parsed and ph_current and e_parsed >= ph_current:
                    self.add_error('iron_folic_end', f"Iron w/ Folic Acid (completed): today's date and future dates are not allowed. Please enter a date before {ph_current}.")
                    return cleaned_data
        return cleaned_data