from django import forms

PAYMENT_METHOD_CHOICES = [
    ("", "— Select Payment Method —"),
    (1, "CASH"),
    (2, "GCASH"),
    (3, "CARD"),
    (4, "WAIVED"),
    (5, "ONLINE GCASH"),
]

MONTH_CHOICES = [
    ("", "— Select Month —"),
    (1, "January"),
    (2, "February"),
    (3, "March"),
    (4, "April"),
    (5, "May"),
    (6, "June"),
    (7, "July"),
    (8, "August"),
    (9, "September"),
    (10, "October"),
    (11, "November"),
    (12, "December"),
]

class ORFilters(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'search',
            'class' : 'form-control', 
            'placeholder' : 'Search',
        }),
        label= 'Search',
        required= False,
    )
    pay_meth = forms.ChoiceField(
        choices= PAYMENT_METHOD_CHOICES,
        widget=forms.Select(attrs={
            'id' : 'pay_meth',
            'class' : 'form-select',
        }),
        label= 'Payment Method',
        required= False,
    )
    month = forms.ChoiceField(
        choices=MONTH_CHOICES,
        widget=forms.Select(attrs={
            'id': 'month',
            'class': 'form-select',
        }),
        label='Month',
        required=False,
    )
    year = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'id': 'year',
            'class': 'form-control',
            'placeholder': 'Year',
            'min': '2000',
        }),
        label='Year',
        required=False,
    )
    date_from = forms.DateField(
        widget=forms.DateInput(attrs={
            'id': 'date_from',
            'class': 'form-control',
            'type': 'date',
        }),
        label='Date From',
        required=False,
    )
    date_to = forms.DateField(
        widget=forms.DateInput(attrs={
            'id': 'date_to',
            'class': 'form-control',
            'type': 'date',
        }),
        label='Date To',
        required=False,
    )


class RequestedDocsFilters(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'search',
            'class' : 'form-control', 
            'placeholder' : 'Search',
        }),
        label= 'Search',
        required= False,
    )
    doc_type = forms.ChoiceField(
        choices= [],
        widget=forms.Select(attrs={
            'id' : 'b_type',
            'class' : 'form-select',
        }),
        label= 'Document Type',
        required= False,
    )