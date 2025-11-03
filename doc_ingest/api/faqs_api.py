import logging
import json

from django.http import JsonResponse, HttpRequest
from django.views import View

from dependency_injector.wiring import inject, Provide
from barug.containers import app

from src.app.services.faq_ingestion_service import FAQIngestionService
from src.app.transfer_objects.dto.faq_dto import FAQDTO

logger = logging.getLogger(__name__)


class FAQListAPI(View):
    """Simple GET endpoint to retrieve FAQs from the upstream function.

    URL patterns support both a versioned path and an unversioned default.
    """

    @inject
    def get(self, request: HttpRequest, version: str = "1", service: FAQIngestionService = Provide[app.faq_ingestion_service], *args, **kwargs):
        # Resolve service provider if wiring not applied
        try:
            need_resolve = not service or not hasattr(service, 'fetch_faqs')
        except Exception:
            need_resolve = True

        if need_resolve:
            try:
                service = app.faq_ingestion_service()
            except Exception:
                from src.infra.gateways.faq_ingestion_gateway import FAQIngestionGateway
                from src.app.services.faq_ingestion_service import FAQIngestionService

                service = FAQIngestionService(FAQIngestionGateway())

        try:
            faqs = service.fetch_faqs(version)

            data = []
            # service.fetch_faqs may return DTO instances or plain dicts depending
            # on implementation. Normalize to only question/answer for clients.
            for f in faqs:
                if hasattr(f, "__dict__"):
                    src = f.__dict__
                elif isinstance(f, dict):
                    src = f
                else:
                    # Fallback: try to read attributes
                    src = {
                        "question": getattr(f, "question", ""),
                        "answer": getattr(f, "answer", ""),
                    }

                data.append({
                    "question": src.get("question") if isinstance(src, dict) else "",
                    "answer": src.get("answer") if isinstance(src, dict) else "",
                })

            return JsonResponse({"success": True, "data": data}, status=200)
        except Exception as exc:
            logger.exception("Failed fetching FAQs: %s", exc)
            return JsonResponse({"success": False, "message": "Failed to fetch FAQs."}, status=502)
