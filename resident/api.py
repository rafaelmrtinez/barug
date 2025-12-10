from django.views import View
from django.http import HttpRequest, JsonResponse, HttpResponseBadRequest, HttpResponse
import json
import logging

from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.queries.person_queries import PersonQuery
from src.infra.repositories.commands.household_commands import HouseholdCommand
from src.infra.exceptions.household_membership_exception import HouseholdMembershipException
from src.app.services.household_create_service import HouseholdCreateService

logger = logging.getLogger(__name__)


class ResidentSearchAPI(View):
	"""Class-based API view to search for person(s) and return JSON.

	Query parameters supported (GET):
	- id=<int>           -> returns single person by person_id
	- code=<person_code> -> returns single person by person_code
	- q=<text>           -> free-text search over active people (returns list)
	- limit=<int>        -> optional limit for list searches
	"""

	def get(self, request, *args, **kwargs):
		# pick up params
		person_id = request.GET.get('id')
		person_code = request.GET.get('code')
		q = request.GET.get('q')
		limit = request.GET.get('limit')
		logger.info(
			"ResidentSearchAPI GET called: id=%s code=%s q=%s limit=%s remote=%s",
			person_id,
			person_code,
			q,
			limit,
			request.META.get('REMOTE_ADDR', '<unknown>'),
		)

		try:
			limit_val = int(limit) if limit is not None else None
		except ValueError:
			return HttpResponseBadRequest('invalid limit')

		ctx = ConnectionAdapter()
		pq = PersonQuery(ctx)
		try:
			if person_id:
				try:
					pid = int(person_id)
				except ValueError:
					return HttpResponseBadRequest('invalid id')
				person = pq.get_person_by_id(pid)
				logger.info('ResidentSearchAPI: found person by id=%s', pid)
				return JsonResponse(person, safe=False)

			if person_code:
				person = pq.get_person_by_code(person_code)
				logger.info('ResidentSearchAPI: found person by code=%s', person_code)
				return JsonResponse(person, safe=False)

			if q:
				rows = pq.search_active_people_by_key(q, limit=limit_val)
				logger.info('ResidentSearchAPI: search returned %d rows for q="%s"', len(rows) if rows is not None else 0, q)
				return JsonResponse(rows, safe=False)

			return HttpResponseBadRequest('missing query parameter: one of id, code, or q is required')
		except Exception as exc:
			logger.exception('Unhandled exception in ResidentSearchAPI.get')
			# Return 500 with minimal information; logs contain details
			return HttpResponse(status=500, content=str(exc))


class HouseholdCreateAPI(View):
	"""Accept POSTed household data (JSON or form-encoded) and create a household.

	Expected fields (JSON keys or form names):
	- house_type_id or p_house_type_id
	- house_ownership_id or p_house_ownership_id
	- city or p_city
	- barangay or p_barangay
	- purok_sitio or sitio_purok or p_sitio_purok
	- street or p_street
	- added_by_id or p_added_by_id
	- household_num or p_household_num
	- house_num or p_house_num
	- household_head_id or p_household_head_id
	- latitude (optional)
	- longitude (optional)
	"""
 
	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		self._service: HouseholdCreateService | None = HouseholdCreateService(
      household_command=HouseholdCommand(
          ctx=ConnectionAdapter()
          )
      )

	def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponseBadRequest | JsonResponse | HttpResponse:
		# Accept both JSON and form-encoded data
		logger.info('HouseholdCreateAPI POST called (content_type=%s from=%s)', request.content_type, request.META.get('REMOTE_ADDR', '<unknown>'))
		if request.content_type and request.content_type.startswith('application/json'):
			try:
				data = json.loads(request.body.decode('utf-8') or '{}')
			except Exception:
				logger.warning('HouseholdCreateAPI: invalid JSON body')
				return HttpResponseBadRequest('invalid JSON body')
		else:
			# QueryDict -> regular dict access
			data = {k: v for k, v in request.POST.items()}
		logger.debug('HouseholdCreateAPI: raw payload keys=%s', list(data.keys()))

		# helper to pick field from multiple possible keys
		def pick(*keys):
			for k in keys:
				if k in data and data[k] is not None and data[k] != '':
					return data[k]
			return None

		try:
			p_house_type_id = int(pick('house_type_id', 'p_house_type_id'))
			p_house_ownership_id = int(pick('house_ownership_id', 'p_house_ownership_id'))
			p_city = pick('city', 'p_city')
			p_barangay = pick('barangay', 'p_barangay')
			p_sitio_purok = pick('purok_sitio', 'sitio_purok', 'p_sitio_purok')
			p_street = pick('street', 'p_street')
			p_household_num = pick('household_num', 'p_household_num')
			p_house_num = pick('house_num', 'p_house_num')
			p_household_head_id = int(pick('household_head_id', 'p_household_head_id', 'household_head'))
			lat = pick('p_latitude', 'lat')
			lng = pick('p_longitude', 'lng', 'long')

			p_latitude = float(lat) if lat not in (None, '') else None
			p_longitude = float(lng) if lng not in (None, '') else None
		except TypeError as e:
			return HttpResponseBadRequest('missing required field or invalid type')
		except ValueError as e:
			logger.warning('HouseholdCreateAPI: invalid numeric value: %s', e)
			return HttpResponseBadRequest('invalid numeric value')

		# Basic presence checks
		if not all([p_city, p_barangay, p_household_num, p_house_num]):
			logger.warning('HouseholdCreateAPI: missing required address/household fields')
			return HttpResponseBadRequest('missing required address/household fields')

		try:
			staff = request.session.get('auth') and request.session.get('auth').get('staff_id')
			logger.info('HouseholdCreateAPI: creating household by staff_id=%s for head_id=%s', staff, p_household_head_id)
			logger.debug('HouseholdCreateAPI: insert params: city=%s barangay=%s purok=%s street=%s household_num=%s house_num=%s lat=%s lng=%s', p_city, p_barangay, p_sitio_purok, p_street, p_household_num, p_house_num, p_latitude, p_longitude)
			result = self._service.create_household(
				p_house_type_id,
				p_house_ownership_id,
				p_city,
				p_barangay,
				p_sitio_purok,
				p_street,
				request.session.get('auth').get('staff_id', {}),
				p_household_num,
				p_house_num,
				p_household_head_id,
				p_latitude,
				p_longitude,
			)
			logger.info('HouseholdCreateAPI: service.create_household returned result=%s', result)
			return JsonResponse({'result': result}, status=201)
		except HouseholdMembershipException as he:
			logger.warning('HouseholdCreateAPI: membership exception: %s', getattr(he, 'message', str(he)))
			return JsonResponse({'error': getattr(he, 'message', str(he))}, status=400)
		except Exception as exc:
			logger.exception('Unhandled exception in HouseholdCreateAPI.post')
			return HttpResponse(status=500, content="Something went wrong while creating household.")

