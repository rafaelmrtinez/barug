from django import forms

PAYMENT_METHOD_CHOICES = [
    ("", "— Select Payment Method —"),
    (1, "CASH"),
    (2, "GCASH"),
    (3, "CARD"),
    (4, "WAIVED"),
    (5, "ONLINE GCASH"),
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