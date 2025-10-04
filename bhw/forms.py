from django import forms

BMI_CHOICES = (
    (1, "Low"),
    (2, "Normal"),
    (3, "High"),
)

class ChildHealtheRecordForm(forms.Form):
    """VALIDATION TO BE IMPLEMENTED IN BHW add_child VIEW"""
    child_id = forms.CharField(label="Child ID", max_length=20)
    mother_id = forms.IntegerField(label="Mother ID")
    father_id = forms.IntegerField(label="Father ID", required=False)
    birth_order = forms.CharField(label="Birth Order", max_length=50)
    delivery_place_type_id = forms.IntegerField(label="Delivery Place Type ID")
    family_id = forms.CharField(label="Family ID", max_length=20)

class MaternalBhwIntakeForm(forms.Form):
    # Required
    person_id   = forms.IntegerField(widget=forms.HiddenInput())
    husband_id  = forms.IntegerField(required=False, widget=forms.HiddenInput())
    family_id = forms.IntegerField(label="Family ID", required=False)

    # Anthropometrics
    weight = forms.DecimalField(label="Weight (kg)", required=False, min_value=0, decimal_places=2)
    height = forms.DecimalField(label="Height (cm)", required=False, min_value=0, decimal_places=2)
    bmi_status_id = forms.ChoiceField(label="BMI Status", choices=BMI_CHOICES, required=False)

    # Plans
    place_of_delivery_plan = forms.CharField(label="Planned Place of Delivery", required=False)
    newborn_screening_plan = forms.BooleanField(label="Newborn screening planned?", required=False)

    # Past medical/obstetric history
    prev_illness = forms.CharField(widget=forms.Textarea, required=False, label="Previous illness")
    prev_hospitalization = forms.CharField(widget=forms.Textarea, required=False, label="Previous hospitalization")
    prev_preg_complication = forms.CharField(widget=forms.Textarea, required=False, label="Previous pregnancy complications")

    num_children_born_alive = forms.IntegerField(required=False, min_value=0, label="# children born alive")
    num_children_living = forms.IntegerField(required=False, min_value=0, label="# living children")
    num_abortion = forms.IntegerField(required=False, min_value=0, label="# abortions")
    num_stillbirth = forms.IntegerField(required=False, min_value=0, label="# stillbirths")
    num_large_babies = forms.IntegerField(required=False, min_value=0, label="# large babies (>8lbs)")

    has_diabetes = forms.BooleanField(required=False, label="Diabetes")
    gravida = forms.IntegerField(required=False, min_value=0, label="Gravida")
    para = forms.IntegerField(required=False, min_value=0, label="Para")

    # Optional multi-selects (IDs from reference tables if you have them)
    checklist_item_ids = forms.CharField(
        required=False,
        help_text="Comma-separated checklist item IDs (optional)"
    )
    risk_category_ids = forms.CharField(
        required=False,
        help_text="Comma-separated risk category IDs (optional)"
    )

    # NOTE: Midwife fields intentionally omitted here; passed as None on create.


class SearchActiveScheduleFilter(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'search',
            'class' : 'form-control', 
            'placeholder' : 'Search',
    }),
        label= 'Search',
        required= False,
    )

class StatusActiveScheduleFilter(forms.Form):
    status = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={
            'id' : 'status',
            'class' : 'form-select',
        }),
        label= 'Status',
        # required= False,
    )
    
    def __init__(self, *args, **kwargs):
        from src.infra.database.connection_adapter import ConnectionAdapter
        from src.infra.repositories.account_status_repository import AccountStatusRepository
        super().__init__(*args, **kwargs)
        status = AccountStatusRepository(ConnectionAdapter())
        self.fields['status'].choices = [('', 'All')] + [(str(row[0]), row[1]) for row in status.get_all()]

class WeekRangeActiveScheduleFilter(forms.Form):
    week_range = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={
            'id' : 'week_range',
            'class' : 'form-select',
        }),
        label= "Week Range",
        # required= False,
    )
    
    def __init__(self, *args, **kwargs):
        from src.infra.database.connection_adapter import ConnectionAdapter
        from src.infra.repositories.week_range_repository import WeekRangeRepository
        super().__init__(*args, **kwargs)
        week_range = WeekRangeRepository(ConnectionAdapter())
        self.fields['week_range'].choices = [('', 'All')] + [(str(row[0]), row[1]) for row in week_range.get_all()]

class Reschedule(forms.Form):
    week_range = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={
            'id' : 'select-week_range',
            # 'class' : 'form-select',
        }),
        label= 'Week Range',
        required= True,
    )

    reason = forms.ChoiceField(
        choices=[
            ('No one at home', 'No one at home'),
            ('Household requested new date', 'Household requested new date'),
            ('Emergency in household', 'Emergency in household'),
            ('Bad weather conditions', 'Bad weather conditions'),
            ('Health worker unavailable', 'Health worker unavailable'),
            ('Barangay activity conflict', 'Barangay activity conflict'),
            ('Incorrect address given', 'Incorrect address given'),
            ('Ongoing household event (e.g., wake, celebration)', 'Ongoing household event (e.g., wake, celebration)'),
            ('Security/safety concern', 'Security/safety concern'),
            ('Access to area restricted', 'Access to area restricted'),
            ],
        widget=forms.Select(attrs={
            'id' : 'reschedule',
            'class' : 'form-select',
        }),
        label= 'Reason',
        # required= False,
    )
