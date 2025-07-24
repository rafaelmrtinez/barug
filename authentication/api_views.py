import jwt, datetime, requests, json
# import datetime
# import requests
# import json
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from supabase_client import supabase, SUPABASE_URL,  SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY # Your Supabase wrapper
from django.db import connection, transaction
from django.shortcuts import render
from django.http import JsonResponse

# For Google SMTP
from django.core.mail import send_mail, BadHeaderError


# SendGrid API, Verified sender Email, Name displayed in inbox
SENDGRID_API_KEY = settings.SENDGRID_API_KEY
SENDGRID_FROM_EMAIL = settings.SENDGRID_FROM_EMAIL
SENDGRID_FROM_NAME = settings.SENDGRID_FROM_NAME

EMAIL_HOST_USER = settings.EMAIL_HOST_USER

# Secret for encoding/decoding JWTs
JWT_SECRET = settings.SECRET_KEY
JWT_ALGORITHM = "HS256"


class ResidentLoginView(APIView):
    """
    Resident login API view
    """
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        # Basic validation
        if not username or not password:
            return Response(
                {"error": "Username and password are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Call Supabase stored procedure user_login()
            response = supabase.rpc("user_login", {
                "p_username": username,
                "p_password": password
            }).execute()

            # ✅ Check if data was returned
            user_data = response.data

            if not user_data:
                return Response(
                    {"error": "Invalid username or password."},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            # Supabase returns: [{'user_id': 3, 'user_type': 'PERSON'}]
            user = user_data[0]  # Get first row from result

            # JWT payload
            payload = {
                "user_id": user.get("user_id"),
                "username": username,
                "role": user.get("user_type", "PERSON"),  # use db user_type
                "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)  # Token expiry
            }
            token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
                
            return Response({
                "message": "Login successful.",
                "token": token,
                "user": {
                    "user_id": user.get("user_id"),
                    "username": username,
                    "role": user.get("user_type", "PERSON")
                }
            }, status=status.HTTP_200_OK)   

        except Exception as e:
            # [DEBUG] print("Login error:", e)

            # If Supabase error dict is passed in e.args[0]
            if hasattr(e, 'args') and isinstance(e.args[0], dict):
                # Replace Python None with JSON null automatically
                error_data = e.args[0]
                # Optional: remove unneeded fields
                error_response = {
                    "message": error_data.get("message"),
                    "code": error_data.get("code")
                }
                return Response(
                    error_response,
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Generic fallback error
            return Response(
                {"message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class EmailConfirmedAPIView(APIView):
    """
    Handles Supabase email confirmation
    """

    def get(self, request):
        """
        Handle GET request when Supabase redirects here after email verification
        """
        token = request.GET.get("access_token")
        error = request.GET.get("error")
        error_desc = request.GET.get("error_description")

        if not token:
            return render(request, "authentication/email_confirmed.html", {
                "error": error,
                "error_description": error_desc
            })

        try:
            # ✅ Decode Supabase JWT (skip signature verification)
            payload = jwt.decode(token, options={"verify_signature": False})
            auth_user_id = payload.get("sub")
            email = payload.get("email")

            # [DEBUG] print("Supabase auth_user_id (credential_id):", auth_user_id)
            # [DEBUG] print("Supabase email:", email)

            if not auth_user_id or not email:
                return render(request, "authentication/email_confirmed.html", {
                    "error": "Invalid token payload.",
                    "error_description": "Missing user ID or email."
                })

            # ✅ Get the person_id using credential_id
            credential_resp = supabase.table("person_credential") \
                .select("person_id") \
                .eq("credential_id", auth_user_id) \
                .single() \
                .execute()

            if not credential_resp.data:
                # [DEBUG] print("No matching credential found for auth_user_id.")
                return render(request, "authentication/email_confirmed.html", {
                    "error": "Account not found.",
                    "error_description": "No linked resident account found for this Supabase user."
                })

            person_id = credential_resp.data["person_id"]
            # [DEBUG] print("Found person_id:", person_id)

            # ✅ Update is_email_verified in person table
            update_resp = supabase.table("person") \
                .update({"is_email_verified": True}) \
                .eq("person_id", person_id) \
                .execute()

            # [DEBUG] print("Update response:", update_resp)

            return render(request, "authentication/email_confirmed.html", {
                "error": None,
                "error_description": None,
                "email": email,
                "extra_msg": "Your email has been successfully verified."
            })

        except Exception as e:
            # [DEBUG] print("Email confirmation error:", e)
            return render(request, "authentication/email_confirmed.html", {
                "error": "Internal Server Error",
                "error_description": str(e)
            })

    def post(self, request):
        """
        Handle POST requests (for mobile/web clients)
        """
        token = request.data.get("access_token")
        if not token:
            return Response(
                {"error": "Missing access_token."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # ✅ Decode Supabase JWT (skip signature verification)
            payload = jwt.decode(token, options={"verify_signature": False})
            auth_user_id = payload.get("sub")
            email = payload.get("email")

            # [DEBUG] print("Supabase auth_user_id (credential_id):", auth_user_id)
            # [DEBUG] print("Supabase email:", email)

            if not auth_user_id or not email:
                return Response(
                    {"error": "Invalid token payload."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # ✅ Get the person_id using credential_id
            credential_resp = supabase.table("person_credential") \
                .select("person_id") \
                .eq("credential_id", auth_user_id) \
                .single() \
                .execute()

            if not credential_resp.data:
                # [DEBUG] print("No matching credential found for auth_user_id.")
                return Response(
                    {"error": "No linked resident account found."},
                    status=status.HTTP_404_NOT_FOUND
                )

            person_id = credential_resp.data["person_id"]
            # [DEBUG] print("Found person_id:", person_id)

            # ✅ Update is_email_verified in person table
            update_resp = supabase.table("person") \
                .update({"is_email_verified": True}) \
                .eq("person_id", person_id) \
                .execute()

            # [DEBUG] print("Update response:", update_resp)

            return Response(
                {
                    "message": "Email confirmed successfully. Account linked.",
                    "auth_user_id": auth_user_id,
                    "email": email
                },
                status=status.HTTP_200_OK
            )

        except Exception as e:
            # [DEBUG] print("Email confirmation error:", e)
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ResendVerificationEmailAPIView(APIView):
    """
    Resend the email verification for a user
    by generating a new confirmation link and sending it via Gmail SMTP.
    """
    def post(self, request):
        try:
            # ✅ Step 1: Parse request
            email = request.data.get("email")
            if not email:
                return Response(
                    {"error": "Email is required."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            # [DEBUG] print(f"📥 Parsed email: {email}")

            # ✅ Step 2: Generate confirmation link from Supabase
            generate_link_url = f"{SUPABASE_URL}/auth/v1/admin/generate_link"
            headers = {
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"
            }
            payload = {
                "type": "signup",
                "email": email
            }
            generate_resp = requests.post(generate_link_url, headers=headers, json=payload)
            # [DEBUG] print("Supabase generate_link response status:", generate_resp.status_code)

            if generate_resp.status_code not in [200, 201]:
                return Response(
                    {"error": "Failed to generate confirmation link."},
                    status=generate_resp.status_code
                )

            result = generate_resp.json()
            action_link = result.get("action_link", "").replace("\\u0026", "&")
            # [DEBUG] print(f"🔗 Fixed Action Link: {action_link}")

            if not action_link:
                return Response(
                    {"error": "No confirmation link was generated."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # ✅ Step 3: Send email via Django's send_mail (Gmail SMTP)
            subject = "Confirm Your BaRUG Account"
            message = ""
            html_message = f"""
                <h1>Confirm Your Account</h1>
                <p>Hello,</p>
                <p>Click the button below to confirm your email address and activate your BaRUG account:</p>
                <p><a href="{action_link}" style="padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px;">Confirm Email</a></p>
                <p>If you didn’t request this, you can safely ignore it.</p>
            """

            send_mail(
                subject,
                message,  # Plain text fallback (empty here)
                'raphaelbellosillo1230@gmail.com',  # From email (your Gmail)
                [email],  # To email
                fail_silently=False,
                html_message=html_message
            )
            # [DEBUG] print("✅ Email sent via Gmail SMTP.")

            return Response(
                {
                    "message": "Verification email sent successfully.",
                    "action_link": action_link  # For debugging
                },
                status=status.HTTP_200_OK
            )

        except Exception as e:
            # [DEBUG] print("❌ Resend verification error:", str(e))
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ForgotPasswordAPIView(APIView):
    """
    API to send password reset link to user email
    """
    def post(self, request):
        email = request.data.get("email")
        if not email:
            return Response(
                {"error": "Email is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # ✅ Step 1: Generate recovery link from Supabase with custom redirect URL
            # print("SUPABASE_URL:", SUPABASE_URL)
            # print("SERVICE_ROLE_KEY:", SUPABASE_SERVICE_ROLE_KEY)

            supabase_url = f"{SUPABASE_URL}/auth/v1/admin/generate_link"
            headers = {
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"
            }
            payload = {
                "type": "recovery",
                "email": email,

                "redirect_to": f"{settings.TESTING_URL_USED}/authentication/forgot_password/new_password"   # 👈 Custom URL
            }

            supabase_url = f"{SUPABASE_URL}/auth/v1/admin/generate_link"
            # print("Calling Supabase URL:", supabase_url)

            response = requests.post(supabase_url, headers=headers, json=payload)
            if response.status_code not in [200, 201]:
                return Response(
                    {"error": "Failed to generate password reset link."},
                    status=response.status_code
                )
            
            # print("Response status:", response.status_code)
            # print("Response body:", response.text)

            if response.status_code in [200, 201]:
                data = response.json()
                reset_link = data.get("action_link")

                if not reset_link:
                    # print("❌ Supabase returned no reset link:", data)
                    return Response(
                        {"error": "Supabase did not return a reset link."},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )

                # Replace \u0026 with & if needed
                if "\\u0026" in reset_link:
                    reset_link = reset_link.replace("\\u0026", "&")

                # ✅ Send Gmail email
                subject = "Reset Your BaRUG Account Password"
                html_message = f"""
                    <h1>Password Reset Request</h1>
                    <p>Hello,</p>
                    <p>Click the button below to reset your password:</p>
                    <p><a href="{reset_link}" style="padding: 10px 20px; background-color: #28a745; color: white; text-decoration: none; border-radius: 5px;">Reset Password</a></p>
                    <p>If you didn’t request this, you can safely ignore this email.</p>
                """

                try:
                    send_mail(
                        subject,
                        "",  # Plain text fallback
                        EMAIL_HOST_USER,
                        [email],
                        fail_silently=False,
                        html_message=html_message
                    )
                except BadHeaderError as bhe:
                    return Response(
                        {"error": "Invalid header found."},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                except Exception as smtp_error:
                    return Response(
                        {"error": f"Failed to send email: {str(smtp_error)}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                return Response(
                    {"message": "Password reset link sent successfully."},
                    status=status.HTTP_200_OK
                )

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ResetPasswordAPIView(APIView):
    """
    Handles password reset:
    - GET: Render new_password.html form
    - POST: Reset user password using Supabase Auth API + DB function
    """

    def get(self, request):
        """
        Render the password reset form with access_token
        """
        access_token = request.GET.get("access_token")

        if not access_token:
            # print("⚠️ No access_token in query params. Frontend JS will attempt to extract from URL hash.")
            pass

        return render(request, "authentication/forgot_password/new_password.html")

    def post(self, request):
        """
        Reset password
        """
        token = request.data.get("access_token") or request.POST.get("access_token")
        new_password = request.data.get("new_password") or request.POST.get("new_pass")
        confirm_password = request.data.get("confirm_password") or request.POST.get("confirm_pass")

        # 🟢 Validation
        if not token or not new_password or not confirm_password:
            return JsonResponse(
                {"error": "All fields are required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if new_password != confirm_password:
            return JsonResponse(
                {"error": "Passwords do not match."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if len(new_password) < 8:
            return JsonResponse(
                {"error": "Password must be at least 8 characters long."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # 🟢 Step 1: Fetch Supabase Auth user UUID from recovery token
            user_info_url = f"{SUPABASE_URL}/auth/v1/user"
            headers = {
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {token}"
            }

            user_response = requests.get(user_info_url, headers=headers)
            if user_response.status_code != 200:
                return JsonResponse(
                    {"error": "Invalid or expired reset link."},
                    status=user_response.status_code
                )
            user_data = user_response.json()
            auth_user_id = user_data.get("id")  # Supabase Auth UUID

            # 🟢 Step 2: Update password in Supabase Auth
            update_url = f"{SUPABASE_URL}/auth/v1/user"
            update_payload = {"password": new_password}
            update_response = requests.put(update_url, headers=headers, json=update_payload)
            if update_response.status_code not in [200, 201]:
                return JsonResponse(
                    {"error": "Failed to update password in Supabase Auth."},
                    status=update_response.status_code
                )

            # 🟢 Step 3: Sync new password in person_credential (hashed in DB)
            rpc_response = supabase.rpc("reset_person_password", {
                "p_credential_id": auth_user_id,
                "p_new_password": new_password
            }).execute()

            # ✅ Check for result
            if rpc_response.data is None:
                return JsonResponse(
                    {"error": "Failed to update password in database."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            return JsonResponse(
                {"message": rpc_response.data},
                status=status.HTTP_200_OK
            )

        except Exception as e:
            # print("❌ Password reset error:", e)
            return JsonResponse(
                {"error": f"Error resetting password: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



# SEND GRID SMTP
    # class ResendVerificationEmailAPIView(APIView):
    #     """
    #     Resend the email verification for a user
    #     by generating a new confirmation link and sending it via SendGrid API.
    #     """
    #     def post(self, request):
    #         try:
    #             # ✅ Step 1: Parse request
    #             email = request.data.get("email")
    #             if not email:
    #                 return Response(
    #                     {"error": "Email is required."},
    #                     status=status.HTTP_400_BAD_REQUEST
    #                 )
    #             # [DEBUG] print(f"📥 Parsed email: {email}")

    #             # ✅ Step 2: Generate confirmation link
    #             generate_link_url = f"{SUPABASE_URL}/auth/v1/admin/generate_link"
    #             headers = {
    #                 "apikey": SUPABASE_SERVICE_ROLE_KEY,
    #                 "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"
    #             }
    #             payload = {
    #                 "type": "signup",
    #                 "email": email
    #             }
    #             generate_resp = requests.post(generate_link_url, headers=headers, json=payload)
    #             # [DEBUG] print("Supabase generate_link response status:", generate_resp.status_code)

    #             if generate_resp.status_code not in [200, 201]:
    #                 return Response(
    #                     {"error": "Failed to generate confirmation link."},
    #                     status=generate_resp.status_code
    #                 )

    #             result = generate_resp.json()
    #             action_link = result.get("action_link", "").replace("\\u0026", "&")
    #             # [DEBUG] print(f"🔗 Fixed Action Link: {action_link}")

    #             if not action_link:
    #                 return Response(
    #                     {"error": "No confirmation link was generated."},
    #                     status=status.HTTP_500_INTERNAL_SERVER_ERROR
    #                 )

    #             # ✅ Step 3: Send email via SendGrid API
    #             sendgrid_url = "https://api.sendgrid.com/v3/mail/send"
    #             sendgrid_headers = {
    #                 "Authorization": f"Bearer {SENDGRID_API_KEY}",
    #                 "Content-Type": "application/json"
    #             }
    #             sendgrid_payload = {
    #                 "personalizations": [
    #                     {
    #                         "to": [{"email": email}],
    #                         "subject": "Confirm Your BaRUG Account"
    #                     }
    #                 ],
    #                 "from": {
    #                     "email": SENDGRID_FROM_EMAIL,
    #                     "name": SENDGRID_FROM_NAME
    #                 },
    #                 "content": [
    #                     {
    #                         "type": "text/html",
    #                         "value": f"""
    #                         <h1>Confirm Your Account</h1>
    #                         <p>Hello,</p>
    #                         <p>Click the button below to confirm your email address and activate your BaRUG account:</p>
    #                         <p><a href="{action_link}" style="padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px;">Confirm Email</a></p>
    #                         <p>If you didn’t request this, you can safely ignore it.</p>
    #                         """
    #                     }
    #                 ]
    #             }
    #             sendgrid_resp = requests.post(sendgrid_url, headers=sendgrid_headers, json=sendgrid_payload)
    #             # [DEBUG] print("SendGrid API response status:", sendgrid_resp.status_code)

    #             if sendgrid_resp.status_code not in [200, 202]:
    #                 # [DEBUG] print("❌ SendGrid error:", sendgrid_resp.text)
    #                 return Response(
    #                     {"error": "Failed to send email via SendGrid."},
    #                     status=sendgrid_resp.status_code
    #                 )

    #             return Response(
    #                 {
    #                     "message": "Verification email sent successfully.",
    #                     "action_link": action_link  # For debugging
    #                 },
    #                 status=status.HTTP_200_OK
    #             )

    #         except Exception as e:
    #             # [DEBUG] print("❌ Resend verification error:", str(e))
    #             return Response(
    #                 {"error": str(e)},
    #                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
    #             )


    # class ResetPasswordAPIView(APIView):
    #     """
    #     Handles password reset:
    #     - GET: Render new_password.html form
    #     - POST: Reset user password using Supabase recovery token
    #     """

    #     def get(self, request):
    #         access_token = request.GET.get("access_token")

    #         # 🟢 Allow page to render even if token missing (frontend JS will handle)
    #         if not access_token:
    #             print("⚠️ No access_token in query params. Frontend will attempt to extract from URL hash.")

    #         return render(request, "authentication/forgot_password/new_password.html")

    #     def post(self, request):
    #         token = request.data.get("access_token") or request.POST.get("access_token")
    #         new_password = request.data.get("new_password") or request.POST.get("new_pass")
    #         confirm_password = request.data.get("confirm_password") or request.POST.get("confirm_pass")

    #         if not token or not new_password or not confirm_password:
    #             return JsonResponse(
    #                 {"error": "All fields are required."},
    #                 status=status.HTTP_400_BAD_REQUEST
    #             )
    #         if new_password != confirm_password:
    #             return JsonResponse(
    #                 {"error": "Passwords do not match."},
    #                 status=status.HTTP_400_BAD_REQUEST
    #             )

    #         try:
    #             # 🟢 Step 1: Reset password in Supabase Auth
    #             supabase_url = f"{SUPABASE_URL}/auth/v1/user"
    #             headers = {
    #                 "apikey": SUPABASE_SERVICE_ROLE_KEY,
    #                 "Authorization": f"Bearer {token}"
    #             }
    #             payload = {"password": new_password}

    #             response = requests.put(supabase_url, headers=headers, json=payload)
    #             if response.status_code not in [200, 201]:
    #                 return JsonResponse(
    #                     {"error": "Failed to reset password. Link may be expired."},
    #                     status=response.status_code
    #                 )

    #             # 🟢 Step 2: Get the user info to extract auth user ID
    #             user_info_url = f"{SUPABASE_URL}/auth/v1/user"
    #             user_response = requests.get(user_info_url, headers=headers)
    #             if user_response.status_code != 200:
    #                 return JsonResponse(
    #                     {"error": "Failed to fetch user information."},
    #                     status=user_response.status_code
    #                 )
    #             user_data = user_response.json()
    #             auth_user_id = user_data.get("id")  # Supabase auth user ID
    #             print(f"✅ Auth user ID: {auth_user_id}")

    #             # 🟢 Step 3: Hash the password (use bcrypt to match existing hashes)
    #             import bcrypt
    #             hashed_pw = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    #             # 🟢 Step 4: Update person_credential table in Supabase
    #             supabase_db_url = f"{SUPABASE_URL}/rest/v1/person_credential?credential_id=eq.{auth_user_id}"
    #             db_headers = {
    #                 "apikey": SUPABASE_SERVICE_ROLE_KEY,
    #                 "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    #                 "Content-Type": "application/json",
    #                 "Prefer": "return=representation"
    #             }
    #             db_payload = {
    #                 "passwordd": hashed_pw,
    #                 "password_status": "CHANGED"
    #             }

    #             db_response = requests.patch(supabase_db_url, headers=db_headers, json=db_payload)
    #             if db_response.status_code not in [200, 204]:
    #                 return JsonResponse(
    #                     {"error": "Password reset but failed to update person_credential table."},
    #                     status=db_response.status_code
    #                 )

    #             return JsonResponse(
    #                 {"message": "Password has been reset successfully."},
    #                 status=status.HTTP_200_OK
    #             )

    #         except Exception as e:
    #             return JsonResponse(
    #                 {"error": f"Error resetting password: {str(e)}"},
    #                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
    #             )
