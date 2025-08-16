from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


from src.core.exceptions.domain_exceptions import DomainException
from src.infra.exceptions.supabase_sdk.family_member_exist import FamilyMemberAlreadyExistException
from src.infra.exceptions.supabase_sdk.foreign_key import ForeignKeyException
from src.infra.exceptions.supabase_sdk.missing_response import MissingResponseException
from src.infra.exceptions.supabase_sdk.pending_join_family_request import PendingFamilyRequestException
from src.infra.exceptions.misc.const import FRIENDLY_ERROR

def custom_exception_handler(exc, ctx):
    response = exception_handler(exc, ctx)
    if response is not None:
        return response

    exception_mapping = {
        MissingResponseException: (status.HTTP_500_INTERNAL_SERVER_ERROR, FRIENDLY_ERROR),
        ForeignKeyException: (status.HTTP_400_BAD_REQUEST, FRIENDLY_ERROR),
        DomainException: (status.HTTP_400_BAD_REQUEST, str(exc)),
        PendingFamilyRequestException: (status.HTTP_400_BAD_REQUEST, getattr(exc, "message", str(exc))),
        FamilyMemberAlreadyExistException: (status.HTTP_400_BAD_REQUEST, getattr(exc, "message", str(exc))),
    }

    for exc_type, (code, msg) in exception_mapping.items():
        if isinstance(exc, exc_type):
            return Response({"error": msg}, status=code)

    # Final fallback — unhandled exceptions
    return Response({"error": FRIENDLY_ERROR}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)