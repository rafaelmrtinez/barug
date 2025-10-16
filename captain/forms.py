from django import forms

class StaffFilters(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'search',
            'class' : 'form-control', 
            'placeholder' : 'Search Staff',
            'name': 'q'
        }),
        label='Search Staff',
        required= False,
    )
    role = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={
            'id': 'role_filter',
            'class': 'form-select',
            'name': 'role',
        }),
        label='Filter by Role',
        required=False,
    )
    residential_stat = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={
            'id': 'residential_stat',
            'class': 'form-select',
            'name': 'role',
        }),
        label='Residential Status',
        required=False,
    )

    