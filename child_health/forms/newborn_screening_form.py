from django import forms
import datetime

from src.infra.repositories.child_health_record_repository import ChildHealthRecordRepository
from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.forms.form_utils import FormUtils
from src.infra.utilities.custom_date_time_util import DateAndTimeUtility


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
