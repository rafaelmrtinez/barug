from django.views import View
from django.http import JsonResponse
from django.utils.decorators import method_decorator
import logging

from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from src.infra.database.connection_adapter import ConnectionAdapter

from maternal.views import ACCESS

logger = logging.getLogger(__name__)
CONNECTION = ConnectionAdapter()


@method_decorator(session_login_required, name='dispatch')
@method_decorator(role_required(*ACCESS), name='dispatch')
@method_decorator(nocache, name='dispatch')
class FindPersonView(View):
	"""Search endpoint for people (used by frontend autosuggest).

	Accepts GET with `q` query param. Returns JSON in the shape used by
	the previous function-based `find_person_http` endpoint:
	{ok: True, count: N, results: [{id, name, address}, ...]}
	"""

	def get(self, request, *args, **kwargs):
		q = (request.GET.get('q') or '').strip()
		if len(q) < 2:
			return JsonResponse({"ok": True, "count": 0, "results": []})

		try:
			# Local imports to avoid import cycles and keep module-level small
			from src.infra.repositories.queries.person_queries import PersonQuery
			from src.app.adapters.resident_service_adapter import ResidentServiceAdapter
			from src.app.services.resident_service import ResidentService
			from src.infra.repositories.resident_repository import ResidentRepository

			adapter = ResidentServiceAdapter(
				ResidentService(ResidentRepository(CONNECTION)),
				PersonQuery(CONNECTION),
			)

			rows = adapter.get_minors_under5_active()
			results = [
				{"id": r.get("person_id"), "name": r.get("full_name"), "address": r.get("address") or ""}
				for r in rows
			]

			return JsonResponse({"ok": True, "count": len(results), "results": results})

		except Exception as e:
			logger.exception("find_person failed: %s", e)
			return JsonResponse({"ok": False, "error": "Internal Server Error"}, status=500)

