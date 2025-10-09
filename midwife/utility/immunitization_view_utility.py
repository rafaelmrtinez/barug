from datetime import datetime, date
from typing import Any

from src.app.transfer_objects.request.init_chilld_immunization_request import InitialChildImmunizationRequest

class ImmunizationViewUtility:

    @staticmethod
    def parse_immunization_payload(payload: dict[str, Any]) -> list[InitialChildImmunizationRequest]:
        result = []

        for vaccine_name, data in payload.items():
            dto = InitialChildImmunizationRequest(
                name=vaccine_name,
                d0=ImmunizationViewUtility.__parse_date(data.get("d0")),
                d1=ImmunizationViewUtility.__parse_date(data.get("d1")),
                d2=ImmunizationViewUtility.__parse_date(data.get("d2")),
                d3=ImmunizationViewUtility.__parse_date(data.get("d3")),
                wt24h=data.get("wt24h")
            )
            result.append(dto)

        return result

    @staticmethod
    def __parse_date(value):
        if not value:
            return None
        if isinstance(value, date):
            return value
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None