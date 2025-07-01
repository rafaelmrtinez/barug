from django.shortcuts import render, redirect
from .forms import LoginForm
from .forms import ForgotPasswordForm
from .forms import NewPasswordForm
from resident.supabase_client import supabase   # your configured supabase client
from django.contrib import messages

# Create your views here.
def login(request) :
    form = LoginForm()

    return render(request, "authentication_index.html", {
        'form' : form,
    })

def forgot_password(request):
    message = None
    error = None

    if request.method == "POST":
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                # Trigger Supabase password reset email
                resp = supabase.auth.api.reset_password_for_email(email)
                # resp typically doesn't raise error if success, but check if needed
                message = "Password reset email sent! Please check your inbox."
            except Exception as e:
                error = f"Failed to send reset email: {str(e)}"
        else:
            error = "Please enter a valid email."
    else:
        form = ForgotPasswordForm()

    return render(request, "forgot_password.html", {
        'form': form,
        'message': message,
        'error': error,
    })

def new_password(request):
    form = NewPasswordForm(request.POST or None)
    
    # You would typically get token from URL parameters or session
    token = request.GET.get("token")

    if request.method == "POST" and form.is_valid():
        new_pass = form.cleaned_data['new_pass']
        confirm_pass = form.cleaned_data['confirm_pass']

        if new_pass != confirm_pass:
            messages.error(request, "Passwords do not match.")
        else:
            try:
                # Use Supabase API to update password using token
                supabase.auth.api.update_user(token, {"password": new_pass})
                messages.success(request, "Password updated successfully! Please log in.")
                return redirect("login")
            except Exception as e:
                messages.error(request, f"Failed to update password: {e}")

    return render(request, "new_password.html", {'form': form})

def email_sent(request) :
    return render(request, "email_sent.html")