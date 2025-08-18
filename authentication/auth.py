# authentication/auth.py
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import exceptions

class UserLike:
    def __init__(self, uid, role, username):
        self.id = uid
        self.uid = uid
        self.role = role
        self.username = username
        self.is_authenticated = True

class CookieOrHeaderJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        raw_token = None

        # 1) Try Authorization header (mobile)
        header = self.get_header(request)
        if header is not None:
            raw_token = self.get_raw_token(header)

        # 2) Fallback to 'access' cookie (web)
        if raw_token is None:
            raw_token = request.COOKIES.get("access")

        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        user = self._user_from_claims(validated_token)
        return (user, validated_token)

    def _user_from_claims(self, token):
        uid = token.get("uid")
        role = token.get("role")
        username = token.get("username")
        if uid is None:
            raise exceptions.AuthenticationFailed("Token missing 'uid' claim")
        return UserLike(uid=uid, role=role, username=username)

    def get_user(self, validated_token):
        return self._user_from_claims(validated_token)
