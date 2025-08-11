import requests
from django.core.mail import send_mail
from django.conf import settings


def send_signup_confirmation_link(email: str) -> bool:
    """
    Generate Supabase confirmation link and send via Gmail SMTP.
    Returns True if email was sent, False otherwise.
    """
    generate_link_url = f"{settings.SUPABASE_URL}/auth/v1/admin/generate_link"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}"
    }
    payload = {
        "type": "signup",
        "email": email
    }

    generate_resp = requests.post(generate_link_url, headers=headers, json=payload)
    print(generate_resp.json())
    if generate_resp.status_code not in [200, 201]:
        print("❌ Failed to generate confirmation link.")
        return False

    result = generate_resp.json()
    action_link = result.get("action_link", "").replace("\\u0026", "&")

    if not action_link:
        print("❌ No action link returned.")
        return False

    # Send email
    subject = "Confirm Your BaRUG Account"
    html_message = f"""
        <h1>Confirm Your Account</h1>
        <p>Hello,</p>
        <p>Click the button below to confirm your email address and activate your BaRUG account:</p>
        <p><a href="{action_link}" style="padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px;">Confirm Email</a></p>
        <p>If you didn’t request this, you can safely ignore it.</p>
    """

    send_mail(
        subject,
        "",  # plain text fallback
        settings.EMAIL_HOST_USER,
        [email],
        fail_silently=False,
        html_message=html_message
    )

    # [DEBUG] print("📬 Confirmation email sent via Gmail SMTP.")
    return True
