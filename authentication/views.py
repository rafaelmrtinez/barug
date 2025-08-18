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
# authentication/views.py
from django.shortcuts import render, redirect
from django.urls import reverse
from django.conf import settings
import requests

from django.shortcuts import render, redirect
from django.conf import settings
import requests

def login(request):
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["email_username"].strip()
            password = form.cleaned_data["password"]

            api_url = "http://192.168.1.4:8000/api/auth/login/"  # make sure this is correct
            print("[WEB] Calling API:", api_url)
            print("[WEB] Payload:", {"username": username, "password": "***"})

            try:
                r = requests.post(
                    api_url,
                    json={"username": username, "password": password},
                    headers={"Accept": "application/json", "Content-Type": "application/json"},
                    timeout=10,
                )
                print("[WEB] API status:", r.status_code)
                print("[WEB] Raw response (first 500 chars):", r.text[:500])
                r.raise_for_status()
            except requests.RequestException as e:
                print("[WEB] API request failed:", e)
                form.add_error(None, f"Login service is unreachable: {e}")
            else:
                try:
                    data = r.json()
                except ValueError:
                    print("[WEB] Response not JSON decodable")
                    form.add_error(None, "Unexpected response from login service.")
                else:
                    token = data.get("token")
                    user  = data.get("user")
                    print("[WEB] Parsed JSON user:", user)
                    print("[WEB] Token (first 40 chars):", (token[:40] + "...") if token else None)

                    # Save session
                    request.session["user"] = user
                    request.session["auth_token_present"] = bool(token)
                    request.session.save()
                    print("[WEB] Session key:", request.session.session_key)
                    print("[WEB] Session data now:", dict(request.session))

                    # Redirect + set cookie
                    resp = redirect("authentication:email_confirmed")
                    if token:
                        resp.set_cookie(
                            "auth_token",
                            token,
                            httponly=True,
                            secure=not settings.DEBUG,
                            samesite="Lax",
                            max_age=3600,
                            path="/",
                        )
                        print("[WEB] Will set auth_token cookie (HttpOnly, SameSite=Lax).")
                    return resp
    else:
        form = LoginForm()

    return render(request, "authentication_index.html", {"form": form})



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