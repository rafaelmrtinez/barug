from django import forms
from datetime import datetime, date

from barug.utility.custom_date_time_util import DateAndTimeUtility
from src.infra.repositories.child_health_record_repository import ChildHealthRecordRepository
from maternal.forms.maternal_identification_form import add_bootstrap_classes


class ChildBreastFeedingForm(forms.Form):
    """Form for tracking exclusive breastfeeding checks and feeding type."""

    # type_of_feeding = forms.ChoiceField(
    #     label="Type of Feeding",
    #     required=False,
    #     choices=[],
    #     error_messages={'required': 'Please select a type of feeding.'},
    # )

    # Create fields for 5 visits dynamically
    for i in range(1, 6):
        locals()[f"exclusive_bf_check_{i}"] = forms.DateField(
            label=f"Exclusive BF check (Visit {i})",
            required=False,
            widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            error_messages={
                'required': f'Please provide the date for Visit {i}.'
            },
        )
    del i

    form_type = forms.CharField(initial="bf_feeding_form", widget=forms.HiddenInput(attrs={'id': 'id_form_type_bf'}))

    # -------------------- INIT --------------------

    def __init__(self, *args, chr_repo: ChildHealthRecordRepository | None = None,
                 child_health_record_id: int | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._repo = chr_repo
        self._child_health_record_id = child_health_record_id
        self._existing_data = self._repo.fetch_child_details_bf_display_by_chr_id(child_health_record_id)
        
        print(f"Existing BF data: {self._existing_data}")
        # If there are existing breastfeeding check rows, map them to the
        # five visit slots. The earliest visit (lowest visit_id) should map
        # to exclusive_bf_check_1, next to exclusive_bf_check_2, etc.
        if self._existing_data and isinstance(self._existing_data, list):
            try:
                # Ensure chronological order by visit_id ascending
                rows = sorted(self._existing_data, key=lambda r: (r.get('visit_id') or 0))
                existing_dates = []
                for idx, row in enumerate(rows[:5]):
                    field_name = f"exclusive_bf_check_{idx+1}"
                    check_date = row.get('check_date')
                    # normalize datetime -> date
                    if isinstance(check_date, datetime):
                        check_date = check_date.date()
                    elif isinstance(check_date, str):
                        # try parsing ISO date string
                        parsed = DateAndTimeUtility.parse_date(check_date)
                        if parsed:
                            check_date = parsed
                    # only set initial when a date-like value exists
                    if check_date:
                        try:
                            self.fields[field_name].initial = check_date
                            # make populated fields readonly to avoid re-entry
                            self.fields[field_name].disabled = True
                            self.fields[field_name].widget.attrs['readonly'] = True
                            existing_dates.append(check_date)
                        except KeyError:
                            # field not present (shouldn't happen) — skip
                            continue
                # store ordered existing dates for clean() comparisons
                self._existing_dates = existing_dates
            except Exception:
                # non-fatal — leave defaults if anything goes wrong
                pass
        else:
            self._existing_dates = []
    
    def clean(self):
        cleaned_data = super().clean()
        # Quick debug (can be removed or converted to logger.debug)
        print(f"BF Form cleaned data: {cleaned_data}")

        # Build incoming dates in slot order
        slot_fields = [f"exclusive_bf_check_{i}" for i in range(1, 6)]
        incoming = []
        for fname in slot_fields:
            val = cleaned_data.get(fname)
            # Normalize incoming values to date objects when possible
            if isinstance(val, datetime):
                val = val.date()
            elif isinstance(val, str):
                parsed = DateAndTimeUtility.parse_date(val)
                if parsed:
                    val = parsed
            incoming.append(val)

        # If user submitted nothing at all, prompt for at least one date
        if all(v is None for v in incoming):
            self.add_error(None, "Please provide at least one exclusive breastfeeding check date.")
            return cleaned_data

        # Rule: no "holes" — you cannot fill a later visit when an earlier one is empty
        for i in range(len(incoming)):
            if incoming[i] is None and any(incoming[j] is not None for j in range(i+1, len(incoming))):
                self.add_error(None, f"Please fill earlier visit(s) before adding a date for Visit {i+1}.")
                return cleaned_data

        # Build compact lists of non-null incoming dates in order
        incoming_non_null = [d for d in incoming if d is not None]

        # Use timezone-aware current date if utility available
        # DateAndTimeUtility.get_current_date returns an ISO string; parse it
        try:
            ph_today_str = DateAndTimeUtility.get_current_date()
            today = DateAndTimeUtility.parse_date(ph_today_str) or date.today()
        except Exception:
            today = date.today()

        # Prevent future dates
        for d in incoming_non_null:
            if d > today:
                self.add_error(None, "One or more dates are in the future. Please use today or past dates only.")
                return cleaned_data

        existing = getattr(self, '_existing_dates', []) or []

        # If there are existing entries, enforce rules around edits/additions
        if existing:
            # If user attempted to remove existing entries (fewer non-null than existing)
            if len(incoming_non_null) < len(existing):
                self.add_error(None, "Cannot remove previously recorded check dates. To modify existing entries, edit the original record.")
                return cleaned_data

            # Ensure the existing prefix wasn't changed
            prefix = incoming_non_null[: len(existing)]
            if prefix != existing:
                self.add_error(None, "Existing check dates may not be modified. To change them, edit the original record.")
                return cleaned_data

            # If lengths equal and prefix equals, nothing changed
            if len(incoming_non_null) == len(existing):
                self.add_error(None, "No changes detected — the submitted dates match existing records.")
                return cleaned_data

            # incoming has greater length -> new entries appended
            if len(incoming_non_null) > len(existing):
                new_entries = incoming_non_null[len(existing):]
                # ensure new entries are strictly after last existing date and strictly increasing
                last_existing = existing[-1]
                prev = last_existing
                for d in new_entries:
                    if d <= prev:
                        self.add_error(None, "Newly added check dates must be after the previously recorded date.")
                        return cleaned_data
                    prev = d
                # All good — expose last new entry for saving
                cleaned_data['exclusive_bf_check_last'] = new_entries[-1]
                return cleaned_data

        else:
            # No existing entries — validate that incoming_non_null are strictly increasing
            for i in range(1, len(incoming_non_null)):
                if incoming_non_null[i] <= incoming_non_null[i-1]:
                    self.add_error(None, "Breastfeeding check dates must be in chronological order and each date must be later than the previous one.")
                    return cleaned_data
            # If there are incoming entries, set last
            if incoming_non_null:
                cleaned_data['exclusive_bf_check_last'] = incoming_non_null[-1]
                return cleaned_data

        return cleaned_data