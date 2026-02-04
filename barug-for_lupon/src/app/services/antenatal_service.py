from midwife.utility.anc_view_utility import ANCViewUtility
from src.app.contracts.antenatal_service import IAntenatalCareService
from src.app.transfer_objects.request.anc_labolatory_results_request import ANCLaboratoryResultsRequest
from src.app.transfer_objects.request.antenatal_care_request import AntenatalCareRequest
from src.app.transfer_objects.request.tetanus_toxoid_request import TetanusToxoidRequest
from src.domain.contracts.antenatal_care_repository import IAntenatalCareRepository


class AntenatalCareService(IAntenatalCareService):

    def __init__(self, anc_repository: IAntenatalCareRepository):
        self.antenatal_repository = anc_repository

    def execute(self, init_data: AntenatalCareRequest, lab_results: list[ANCLaboratoryResultsRequest], tt_vaccines: list[TetanusToxoidRequest]):
        init_data.p_lab_results = lab_results if lab_results else None
        init_data.p_tt_vaccines = tt_vaccines if tt_vaccines else None
        return self.antenatal_repository.insert_anc_visit(init_data)