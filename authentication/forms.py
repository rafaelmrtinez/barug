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