import logging
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse
from django.core.paginator import Paginator

from src.app.services.faq_ingestion_service import FAQIngestionService

logger = logging.getLogger(__name__)


def faqs_page(request: HttpRequest) -> HttpResponse:
	"""Server-side rendered page that displays FAQs fetched from upstream.

	This view uses the `FAQIngestionService.fetch_faqs` method which returns a
	list of dicts containing only `question` and `answer` keys.
	"""
	# query params
	q = request.GET.get('q', '')
	page = request.GET.get('page', 1)

	try:
		service = FAQIngestionService()
		faqs = service.fetch_faqs(version=1)
	except Exception as exc:
		logger.exception("Failed fetching FAQs: %s", exc)
		faqs = []

	# server-side search filter (case-insensitive substring match)
	if q:
		q_lower = q.strip().lower()
		faqs = [f for f in faqs if q_lower in (f.get('question','').lower() + ' ' + f.get('answer','').lower())]

	# paginate results
	per_page = 10
	paginator = Paginator(faqs, per_page)
	try:
		page_obj = paginator.get_page(page)
	except Exception:
		page_obj = paginator.get_page(1)

	context = {
		"page_title": "Barangay FAQs",
		"faqs": page_obj.object_list,
		"page_obj": page_obj,
		"q": q,
	}
	return render(request, "doc_ingest/faqs.html", context)
