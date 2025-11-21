from django import forms
from datetime import datetime, date

from src.infra.utilities.custom_date_time_util import DateAndTimeUtility
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
