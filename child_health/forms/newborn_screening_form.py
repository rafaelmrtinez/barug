from django import forms
import datetime

from src.infra.repositories.child_health_record_repository import ChildHealthRecordRepository
from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.forms.form_utils import FormUtils
from barug.utility.custom_date_time_util import DateAndTimeUtility


class NewbornScreeningForm(forms.Form):
    
    """
        IMPORTANT NOTE:
    
            This has already been merged into BreastFeedingTypeForm.
        Keeping this here for reference in case we need to revert.
        
        Date: October 19, 2025    
    
    """
    
    referred_for_newborn_screening = forms.DateField(
        label="Date referred for newborn screening",
        required=True,
        widget=forms.DateInput(
            attrs={"type": "date", "class": "form-control"}),
        error_messages={'required': 'Please provide the date referred for newborn screening.'}
    )
    
    type_of_feeding = forms.ChoiceField(
        label="Type of Feeding",
        required=True, 
        choices=[],
        error_messages={'required': 'Please select a type of feeding.'})

    form_type = forms.CharField(widget=forms.HiddenInput(attrs={'id': 'id_form_type_nbs'}), initial="newborn_screening_form")

    def clean(self):
        cleaned_data = super().clean()

        # Validate that the referred date is not in the future.
        # Use a friendly message and return immediately after adding the error
        # so the UI can surface it right away.
        date_field = 'referred_for_newborn_screening'
        referred_date = cleaned_data.get(date_field)

        # Only validate when the form is submitted
        if not getattr(self, 'is_bound', False):
            return cleaned_data

        # If an existing DB record already has both values, prevent re-entry.
        if getattr(self, '_existing_data', None):
            db = self._existing_data
            if isinstance(db, dict) and db.get('feeding_type_name') and db.get('referred_newborn_screening_date'):
                # Build a friendly message using sanitized DB values
                feed_name = str(db.get('feeding_type_name'))
                sanitized_feed, feed_err = FormUtils.sanitize_text(feed_name, "Feeding Type")
                if feed_err:
                    sanitized_feed = feed_name

                db_date = db.get('referred_newborn_screening_date')
                if isinstance(db_date, datetime.datetime):
                    db_date = db_date.date()
                date_display = db_date.isoformat() if isinstance(db_date, datetime.date) else str(db_date)

                self.add_error(None, f"A newborn screening entry already exists for feeding '{sanitized_feed}' on {date_display}. To change it, edit the existing record.")
                return cleaned_data

        # Ensure both fields are present together. Surface a single friendly message
        # if either is missing to encourage the user to provide both values.
        type_val = cleaned_data.get('type_of_feeding')
        # normalize date if it's a string
        if isinstance(referred_date, str):
            referred_date_parsed = DateAndTimeUtility.parse_date(referred_date)
            if referred_date_parsed:
                referred_date = referred_date_parsed
                cleaned_data[date_field] = referred_date

        if type_val in (None, "") or referred_date is None:
            self.add_error(None, "Please provide both a feeding type and the screening date (today or a past date).")
            return cleaned_data

        # Validate that the referred date is not in the future.
        today = datetime.date.today()
        try:
            if referred_date > today:
                msg = (
                    "The screening date cannot be in the future. "
                    "Please choose today or a past date."
                )
                self.add_error(date_field, msg)
                return cleaned_data
        except TypeError:
            # In case the value is not a date object for some reason,
            # add a friendly error and return.
            self.add_error(date_field, "Enter a valid date for newborn screening.")
            return cleaned_data

        # Sanitize feeding label derived from the selected choice
        try:
            feed_label = None
            for val, label in getattr(self, '_feeding_types', []):
                if str(val) == str(type_val):
                    feed_label = label
                    break
            if feed_label:
                sanitized_label, label_err = FormUtils.sanitize_text(str(feed_label), "Feeding Type")
                if label_err:
                    self.add_error('type_of_feeding', label_err)
                    return cleaned_data
                # expose sanitized label for downstream processing
                cleaned_data['type_of_feeding_label'] = sanitized_label
            else:
                # If there is an existing fallback display from DB, sanitize it and expose
                fallback = None
                if getattr(self, '_existing_data', None) and isinstance(self._existing_data, dict):
                    fallback = self._existing_data.get('__feeding_display') or self._existing_data.get('feeding_type_name')
                if fallback:
                    sanitized_fb, fb_err = FormUtils.sanitize_text(str(fallback), "Feeding Type")
                    cleaned_data['type_of_feeding_label'] = sanitized_fb if not fb_err else str(fallback)
        except Exception:
            # Non-fatal: keep original value
            pass

        return cleaned_data

    def __init__(self, chr_repo: ChildHealthRecordRepository, child_health_record_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_bootstrap_classes(self)
        self._repo = chr_repo
        self._chr_id = child_health_record_id
        self._existing_data = self._repo.fetch_new_born_screening_date_by_chr_id(self._chr_id)
        self._feeding_types = self._repo.fetch_all_feeding_type_tuple() or []

        # Populate feeding choices
        self.fields['type_of_feeding'].choices = [('', 'Select Feeding Type')] + list(self._feeding_types)

        # If existing data contains both feeding type and screening date,
        # display them and make the fields readonly to avoid re-entry.
        if self._existing_data and isinstance(self._existing_data, dict):
            ft_name = self._existing_data.get('feeding_type_name')
            ft_date = self._existing_data.get('referred_newborn_screening_date')
            if ft_name and ft_date:
                # Set date initial and make readonly/disabled
                try:
                    if isinstance(ft_date, str):
                        try:
                            ft_date_obj = datetime.date.fromisoformat(ft_date)
                        except Exception:
                            ft_date_obj = None
                    elif isinstance(ft_date, datetime.datetime):
                        ft_date_obj = ft_date.date()
                    elif isinstance(ft_date, datetime.date):
                        ft_date_obj = ft_date
                    else:
                        ft_date_obj = None
                except Exception:
                    ft_date_obj = None

                if ft_date_obj:
                    self.fields['referred_for_newborn_screening'].initial = ft_date_obj
                    self.fields['referred_for_newborn_screening'].disabled = True
                    self.fields['referred_for_newborn_screening'].widget.attrs['readonly'] = True

                # Find the matching feeding type id from fetched tuples and set initial
                chosen_val = None
                try:
                    for val, label in self._feeding_types:
                        if str(label).strip().lower() == str(ft_name).strip().lower():
                            chosen_val = str(val)
                            break
                except Exception:
                    chosen_val = None

                if chosen_val is not None:
                    self.fields['type_of_feeding'].initial = chosen_val
                else:
                    # If we couldn't find the id, present the DB label as a fallback
                    sanitized, err = FormUtils.sanitize_text(str(ft_name), "Feeding Type")
                    self.fields['type_of_feeding'].initial = ''
                    # store fallback for display / messages
                    self._existing_data['__feeding_display'] = sanitized if not err else str(ft_name)

                self.fields['type_of_feeding'].disabled = True
                self.fields['type_of_feeding'].widget.attrs['readonly'] = True
