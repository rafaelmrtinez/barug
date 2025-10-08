from src.app.services.anc_service_utility import ANCServiceUtility
from src.app.contracts.antenatal_service import IAntenatalCareService
from src.app.transfer_objects.request.antenatal_care_request import AntenatalCareRequest
from src.domain.contracts.antenatal_care_repository import IAntenatalCareRepository


class AntenatalCareService(IAntenatalCareService):

    def __init__(self, anc_repository: IAntenatalCareRepository):
        self.antenatal_repository = anc_repository
        
    def execute(self, init_data: AntenatalCareRequest, raw_lab_results: dict, raw_tt_vaccines: dict):
        
        tits = ANCServiceUtility.match_those_tities(raw_tt_vaccines)
        lab_results = ANCServiceUtility.laboratory_results_obj_converter(raw_lab_results)

        init_data.p_lab_results = lab_results if lab_results else None
        init_data.p_tt_vaccines = tits if tits else None
        
        return self.antenatal_repository.insert_anc_visit(init_data)