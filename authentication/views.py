from django.shortcuts import render, redirect
from .forms import LoginForm
from .forms import ForgotPasswordForm
from .forms import NewPasswordForm

# TESTING PHASE
#need back-end for proper assignment
user_fullname = 'lname, fname mname suffix'
user_role = 'Clerk'

user_role_template = user_role.lower().replace(' ', '_')

# Create your views here.
def login(request):
    form = LoginForm()

    return render(request, "authentication_index.html", {
        'form' : form,
    })

def forgot_password(request):
    form = ForgotPasswordForm()

    return render(request, "forgot_password.html", {
        'form': form,

    })

def new_password(request):
    form = NewPasswordForm()
    
    return render(request, "new_password.html", {
        'form' : form,
    })

def email_sent(request):
    return render(request, "email_sent.html")

def email_confirmed(request):
    return render(request, "email_confirmed.html")

def temporary_password(request):
    return render(request, 'temporary_password.html', {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / User Registration Log / Temporary Password',
        'page_title': 'Temporary Password',
        'user_role_template': user_role_template,
    })