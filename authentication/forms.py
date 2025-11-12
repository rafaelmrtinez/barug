from django import forms

class LoginForm(forms.Form):
    email_username = forms.CharField(
        widget=forms.TextInput(attrs={
            'id' : 'username',
            'class' : 'form-control', 
            'placeholder' : 'Email or Username',
    }),
        label= 'Email or Username',
        required= True,
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'id': 'password',
            'class' : 'form-control', 
            'placeholder' : 'Password', 
    }),
        label= 'Password',
        required= True,
    )
    
# ---------------------------------------------------------------------------------------------------------

class ForgotPasswordForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'id' : 'email',
            'class' : 'form-control',
            'placeholder' : 'Enter your email address',
    }),
        label= 'Enter your email address',
        required= True,
    )

# ---------------------------------------------------------------------------------------------------------

class NewPasswordForm(forms.Form):
    new_pass = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'id' : 'new_password',
            'class' : 'form-control',
            'placeholder' : 'Create a new password',
    }),
        label= 'Create a new password',
        required= True,
    )
    confirm_pass = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'id' : 'confirm_password',
            'class' : 'form-control',
            'placeholder' : 'Confirm your new password',
    }),
        label= 'Confirm your new password',
        required= True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add Bootstrap invalid class if errors
        for field_name, field in self.fields.items():
            if self.errors.get(field_name):
                existing_classes = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = existing_classes + " is-invalid"

# ---------------------------------------------------------------------------------------------------------

class ChangePasswordForm(forms.Form):
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter current password',
        }),
        label='Current Password',
        required=True,
    )
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter new password',
        }),
        label='New Password',
        required=True,
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm new password',
        }),
        label='Confirm Password',
        required=True,
    )

class VerificationCodeForm(forms.Form):
    code1 = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control text-center',
            'maxlength': '1',
            'style': 'width: 50px; height: 50px; font-size: 1.2rem; font-weight: bold;'
        }),
        required=True,
    )
    code2 = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control text-center',
            'maxlength': '1',
            'style': 'width: 50px; height: 50px; font-size: 1.2rem; font-weight: bold;'
        }),
        required=True,
    )
    code3 = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control text-center',
            'maxlength': '1',
            'style': 'width: 50px; height: 50px; font-size: 1.2rem; font-weight: bold;'
        }),
        required=True,
    )
    code4 = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control text-center',
            'maxlength': '1',
            'style': 'width: 50px; height: 50px; font-size: 1.2rem; font-weight: bold;'
        }),
        required=True,
    )
    code5 = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control text-center',
            'maxlength': '1',
            'style': 'width: 50px; height: 50px; font-size: 1.2rem; font-weight: bold;'
        }),
        required=True,
    )
    code6 = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control text-center',
            'maxlength': '1',
            'style': 'width: 50px; height: 50px; font-size: 1.2rem; font-weight: bold;'
        }),
        required=True,
    )