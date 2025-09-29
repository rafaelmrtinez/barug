from django import forms

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
