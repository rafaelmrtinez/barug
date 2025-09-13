from django import forms

class SearchBusinessOwner(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'search',
            'class' : 'form-control form-control-sm', 
            'placeholder' : 'Search',
    }),
        label= 'Search by Resident ID or Full Name',
        required= True,
    )