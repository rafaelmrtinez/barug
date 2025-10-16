from django import forms

BUSINESS_CATEGORY_CHOICES = [
    ("", "— Select category —"),
    (40, "Bakeries, Pastry Shop"),
    (39, "Cellphones and Gadget Stores"),
    (27, "Commercial Stalls for Rent"),
    (38, "Computer Shops"),
    (45, "Dry Goods"),
    (36, "Educational Institutions (Private)"),
    (25, "Financial Institutions (Lending Companies)"),
    (31, "Firearms Stores"),
    (43, "Fitness Gyms"),
    (32, "Furniture Shops, Appliance Store"),
    (28, "Gasoline Stations"),
    (42, "General Merchandise"),
    (4,  "Groceries Store"),
    (34, "Hotels, Apartments"),
    (29, "Motorcycle and other Vehicle Dealers"),
    (33, "Motorcycle/Bicycle Supplies Stores"),
    (49, "Night Market"),
    (35, "Restaurants, Canteens"),
    (47, "Sari-Sari Store"),
    (48, "Special Permit"),
    (30, "Specialization Clinics such as Dental Clinics, ENT, Pedia Clinics"),
    (46, "Tailoring Services"),
    (37, "Vehicle Services, Auto Repair Shop"),
    (26, "Videoke Bars"),
    (44, "Water Refilling Stations"),
]

OWNERSHIP_TYPE_CHOICES = [
    ("", "— All ownerships —"),
    (1, "SOLE PROPRIETORSHIP"),
    (2, "PARTNERSHIP"),
    (3, "CORPORATION"),
    (4, "COOPERATIVE"),
    (5, "ONE PERSON CORPORATION"),
    (6, "OTHERS"),
]

BUSINESS_STATUS_CHOICES = [
    ("", "— All statuses —"),
    (1, "ACTIVE"),
    (2, "INACTIVE"),
    (3, "SUSPENDED"),
    (4, "REVOKED"),
    (5, "CLOSED"),
    (6, "EXPIRED"),
]


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

class BusinessFilters(forms.Form):
    search = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'search',
            'class' : 'form-control', 
            'placeholder' : 'Search',
        }),
        label= 'Search',
        required= False,
    )
    b_category = forms.ChoiceField(
        choices= BUSINESS_CATEGORY_CHOICES,
        widget=forms.Select(attrs={
            'id' : 'b_category',
            'class' : 'form-select',
        }),
        label= 'Business Type',
        required= False,
    )
    ownership_type = forms.ChoiceField(
        choices= OWNERSHIP_TYPE_CHOICES,
        widget=forms.Select(attrs={
            'id' : 'ownership_type',
            'class' : 'form-select',
        }),
        label= 'Ownership Type',
        required= False,
    )
    status = forms.ChoiceField(
        choices= BUSINESS_STATUS_CHOICES,
        widget=forms.Select(attrs={
            'id' : 'status',
            'class' : 'form-select',
        }),
        label= 'Status',
        required= False,
    )
 