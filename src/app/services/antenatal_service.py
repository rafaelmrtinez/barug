from src.app.contracts.antenatal_service import IAntenatalCareService
from src.app.transfer_objects.request.antenatal_care_request import AntenatalCareRequest
from src.domain.contracts.antenatal_care_repository import IAntenatalCareRepository


class AntenatalCareService(IAntenatalCareService):

    def __init__(self, anc_repository: IAntenatalCareRepository):
        self.antenatal_repository = anc_repository
        
    def execute(self, request: AntenatalCareRequest):
        return self.antenatal_repository.insert_anc_visit(request)