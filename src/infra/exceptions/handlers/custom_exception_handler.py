import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

from django_ratelimit.exceptions import Ratelimited

from src.app.exceptions.prompt_file_exception import PromptFileException
from src.core.exceptions.domain_exceptions import DomainException
from src.infra.exceptions.data_access_exception import DataAccessException
from src.infra.exceptions.general_infra_exception import InfrastructureException
from src.infra.exceptions.supabase_sdk.family_member_exist import FamilyMemberAlreadyExistException
from src.infra.exceptions.supabase_sdk.foreign_key import ForeignKeyException
from src.infra.exceptions.supabase_sdk.missing_response import MissingResponseException
from src.infra.exceptions.supabase_sdk.pending_join_family_request import PendingFamilyRequestException
from src.infra.exceptions.misc.const import FRIENDLY_ERROR


logger = logging.getLogger(__name__)


def custom_exception_handler(exc, ctx):
    response = exception_handler(exc, ctx)
    if response is not None:
        logger.warning(f"Handled exception in {ctx.get('view')}: {exc}", exc_info=True)
        return response

    exception_mapping = {
        MissingResponseException: (status.HTTP_500_INTERNAL_SERVER_ERROR, FRIENDLY_ERROR),
        ForeignKeyException: (status.HTTP_400_BAD_REQUEST, FRIENDLY_ERROR),
        DomainException: (status.HTTP_400_BAD_REQUEST, str(exc)),
        PendingFamilyRequestException: (status.HTTP_400_BAD_REQUEST, getattr(exc, "message", str(exc))),
        FamilyMemberAlreadyExistException: (status.HTTP_400_BAD_REQUEST, getattr(exc, "message", str(exc))),
        PromptFileException: (status.HTTP_500_INTERNAL_SERVER_ERROR, FRIENDLY_ERROR),
        DataAccessException: (status.HTTP_500_INTERNAL_SERVER_ERROR, FRIENDLY_ERROR),
        InfrastructureException: (status.HTTP_500_INTERNAL_SERVER_ERROR, FRIENDLY_ERROR),
        Ratelimited: (status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests. Please try again later.")
    }

    for exc_type, (code, msg) in exception_mapping.items():
        if isinstance(exc, exc_type):
            logger.error(f"{exc_type.__name__} in {ctx.get('view')}: {exc}", exc_info=True)
            return Response({"error": msg}, status=code)

    logger.critical(f"Unhandled exception in {ctx.get('view')} ({ctx.get('request')}): {exc}", exc_info=True)
    return Response({"error": FRIENDLY_ERROR}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)