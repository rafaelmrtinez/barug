from django import forms

class LoginForm(forms.Form) :
    username = forms.CharField(widget=forms.TextInput(attrs={
        'class' : 'form-control', 
        'placeholder' : 'Username',
        }))
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class' : 'form-control', 
        'placeholder' : 'Password', 
        'id': 'toggle_password',
        }))
    
# ---------------------------------------------------------------------------------------------------------

class ForgotPasswordForm(forms.Form) :
    email = forms.EmailField(widget=forms.EmailInput(attrs={
        'class' : 'form-control',
        'placeholder' : 'Enter your email address',
    }))

# ---------------------------------------------------------------------------------------------------------

class NewPasswordForm(forms.Form) :
    new_pass = forms.CharField(widget=forms.PasswordInput(attrs={
        'class' : 'form-control',
        'placeholder' : 'Create a new password',
        'id' : 'toggle_new_password'
    }))
    confirm_pass = forms.CharField(widget=forms.PasswordInput(attrs={
        'class' : 'form-control',
        'placeholder' : 'Confirm your new password',
        'id' : 'toggle_confirm_password'
    }))