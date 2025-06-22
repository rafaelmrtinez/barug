from django.shortcuts import render
from .forms import LoginForm
from .forms import ForgotPasswordForm
from .forms import NewPasswordForm

# Create your views here.
def login(request) :
    form = LoginForm(request.POST or None)

    return render(request, "authentication_index.html", {
        'form' : form,
    })

def forgot_password(request) :
    form = ForgotPasswordForm(request.POST or None)

    return render(request, "forgot_password.html", {
        'form' : form,
    })

def new_password(request) :
    form = NewPasswordForm(request.POST or None)
    
    return render(request, "new_password.html", {
        'form' : form,
    })

def email_sent(request) :
    return render(request, "email_sent.html")