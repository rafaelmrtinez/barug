from src.infra.exceptions.household_exception import HouseholdException

from django.http import HttpRequest, JsonResponse
from django.views import View

from src.app.services.household_update_service import HouseholdUpdateService
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.commands.household_commands import HouseholdCommand
from src.infra.exceptions.household_update_exception import HouseholdUpdateException

import logging

from src.infra.repositories.queries.household_queries import HouseholdQuery

# --- API endpoint to mark quarterly visit ---
class MarkQuarterlyVisitAPI(View):
    """
    API endpoint to mark a family or household as quarterly visited.
    Expects POSTed JSON with:
      - 'type': 'household' or 'family'
      - 'id': the household_id or family_id
      - 'staff_id': the staff performing the visit
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        ctx = ConnectionAdapter()
        self._logger = logging.getLogger("MarkQuarterlyVisitAPI")
        self._cmd = HouseholdCommand(ctx)

    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        import json
        from django.http import JsonResponse
        try:
            self._logger.info("POST /api/mark-quarterly-visit called")
            try:
                payload = json.loads(request.body.decode('utf-8'))
                self._logger.debug(f"Payload received: {payload}")
            except Exception as e:
                self._logger.error(f"Invalid JSON: {e}")
                return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

            visit_type = payload.get('type')
            visit_id = payload.get('id')
            staff_id = request.session.get("auth").get("staff_id")
            if not visit_type or not visit_id or not staff_id:
                return JsonResponse({"success": False, "error": "Missing required fields: type, id, staff_id"}, status=400)

            if visit_type == 'household':
                result = self._cmd.mark_household_quarterly_visit(p_household_id=visit_id, p_staff_id=staff_id)
            elif visit_type == 'family':
                result = self._cmd.mark_family_quarterly_visit(p_family_id=visit_id, p_staff_id=staff_id)
            else:
                return JsonResponse({"success": False, "error": "Invalid type. Must be 'household' or 'family'."}, status=400)

            self._logger.info(f"Quarterly visit marked for {visit_type} {visit_id} by staff {staff_id}.")
            return JsonResponse({"success": True, "result": result})
        except HouseholdException as he:
            self._logger.warning(f"HouseholdException: {he}")
            return JsonResponse({"success": False, "error": str(he)}, status=400)
        except Exception as exc:
            self._logger.error(f"Unhandled error in mark_quarterly_visit: {exc}")
            return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)

# --- API endpoint to change family head ---
class UpdateFamilyHeadAPI(View):
    """
    API endpoint to update the family head.
    Accepts POSTed JSON with required fields for head change.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        ctx = ConnectionAdapter()
        self._logger = logging.getLogger("HouseholdMembershipAPI")
        self._service: HouseholdUpdateService = HouseholdUpdateService(
            household_cmd=HouseholdCommand(ctx),
            logger=self._logger
        )

    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        import json
        from django.http import JsonResponse
        try:
            self._logger.info("POST /api/update-family-head called")
            # Parse JSON body
            try:
                payload = json.loads(request.body.decode('utf-8'))
                self._logger.debug(f"Payload received: {payload}")
            except Exception as e:
                self._logger.error(f"Invalid JSON: {e}")
                return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

            # Call service
            result = self._service.change_family_head(payload=payload, added_by_id=request.session.get("auth").get("staff_id"))
            self._logger.info("Family head update successful.")
            return JsonResponse({"success": True, "result": result})
        except HouseholdUpdateException as hue:
            self._logger.warning(f"HouseholdUpdateException: {hue}")
            return JsonResponse({"success": False, "error": str(hue)}, status=400)
        except Exception as exc:
            self._logger.error(f"Unhandled error in update_family_head: {exc}")
            return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)

# --- API endpoint to update family information ---
class UpdateFamilyInformationAPI(View):
    """
    API endpoint to update family information.
    Accepts POSTed JSON with required fields for family info update.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        ctx = ConnectionAdapter()
        self._logger = logging.getLogger("HouseholdMembershipAPI")
        self._service: HouseholdUpdateService = HouseholdUpdateService(
            household_cmd=HouseholdCommand(ctx),
            logger=self._logger,
            household_query=HouseholdQuery(ctx)
        )

    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        import json
        from django.http import JsonResponse
        try:
            self._logger.info("POST /api/update-family-information called")
            # Parse JSON body
            try:
                payload = json.loads(request.body.decode('utf-8'))
                self._logger.debug(f"Payload received: {payload}")
            except Exception as e:
                self._logger.error(f"Invalid JSON: {e}")
                return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

            # Call service
            result = self._service.update_family_info(payload=payload, added_by_id=request.session.get("auth").get("staff_id"))
            self._logger.info("Family info update successful.")
            return JsonResponse({"success": True, "result": result})
        except HouseholdUpdateException as hue:
            self._logger.warning(f"HouseholdUpdateException: {hue}")
            return JsonResponse({"success": False, "error": str(hue)}, status=400)
        except Exception as exc:
            self._logger.error(f"Unhandled error in update_family_info: {exc}")
            return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)

class UpdateHouseholdHeadAPI(View):
    """
    API endpoint to update the household head.
    Accepts POSTed JSON with required fields for head change.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        ctx = ConnectionAdapter()
        self._logger = logging.getLogger("HouseholdMembershipAPI")
        self._service: HouseholdUpdateService = HouseholdUpdateService(
            household_cmd=HouseholdCommand(ctx),
            logger=self._logger
        )

    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        import json
        from django.http import JsonResponse
        try:
            self._logger.info("POST /api/update-household-head called")
            # Parse JSON body
            try:
                payload = json.loads(request.body.decode('utf-8'))
                self._logger.debug(f"Payload received: {payload}")
            except Exception as e:
                self._logger.error(f"Invalid JSON: {e}")
                return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

            # Call service
            result = self._service.update_household_head(payload=payload, added_by_id=request.session.get("auth").get("staff_id"))
            self._logger.info("Household head update successful.")
            return JsonResponse({"success": True, "result": result})
        except HouseholdUpdateException as hue:
            self._logger.warning(f"HouseholdUpdateException: {hue}")
            return JsonResponse({"success": False, "error": str(hue)}, status=400)
        except Exception as exc:
            self._logger.error(f"Unhandled error in update_household_head: {exc}")
            return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)

class UpdateHouseholdInformationAPI(View):
    
    """
    API endpoint to add multiple household members.
    Accepts POSTed member data (JSON array of member dicts) and added_by_id.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        ctx = ConnectionAdapter()
        self._logger = logging.getLogger("HouseholdMembershipAPI")
        self._service: HouseholdUpdateService = HouseholdUpdateService(
            household_cmd=HouseholdCommand(ctx),
            logger=self._logger
        )
    
    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        import json
        from django.http import JsonResponse
        try:
            self._logger.info("POST /api/update-household-information called")
            # Parse JSON body
            try:
                payload = json.loads(request.body.decode('utf-8'))
                self._logger.debug(f"Payload received: {payload}")
            except Exception as e:
                self._logger.error(f"Invalid JSON: {e}")
                return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

            # Call service
            result = self._service.update_household_info(payload=payload, added_by_id=request.session.get("auth").get("staff_id"))
            self._logger.info("Household info update successful.")
            return JsonResponse({"success": True, "result": result})
        except HouseholdUpdateException as hue:
            self._logger.warning(f"HouseholdUpdateException: {hue}")
            return JsonResponse({"success": False, "error": str(hue)}, status=400)
        except Exception as exc:
            self._logger.error(f"Unhandled error in update_household_info: {exc}")
            return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)