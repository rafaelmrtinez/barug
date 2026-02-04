from django.views import View
from django.http import JsonResponse
from django.utils.decorators import method_decorator
import logging

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from dependency_injector.wiring import inject, Provide
from src.app.bootstrap.app_containers import AppContainer

from maternal.views import ACCESS

logger = logging.getLogger(__name__)


@method_decorator(session_login_required, name='dispatch')
@method_decorator(role_required(*ACCESS), name='dispatch')
@method_decorator(nocache, name='dispatch')
class SearchMotherAPI(View):
	"""Search endpoint for people (used by frontend autosuggest).

	Accepts GET with `q` query param. Returns JSON in the shape used by
	the previous function-based `find_person_http` endpoint:
	{ok: True, count: N, results: [{id, name, address}, ...]}
	"""

	@inject
	def get(self, request, *args, resident_adapter = Provide[AppContainer.resident_service_adapter], **kwargs):
		q = (request.GET.get('q') or '').strip()
		if len(q) < 2:
			return JsonResponse({"ok": True, "count": 0, "results": []})

		try:
			rows = resident_adapter.search_female_active_by_key(key=q, limit=10)
			print(f"ROWS: {rows}")
			results = [
				{"id": r.get("person_id"), "name": r.get("full_name"), "address": r.get("address") or ""}
				for r in rows
			]

			return JsonResponse({"ok": True, "count": len(results), "results": results})

		except Exception as e:
			logger.exception("find_person failed: %s", e)
			return JsonResponse({"ok": False, "error": "Internal Server Error"}, status=500)

