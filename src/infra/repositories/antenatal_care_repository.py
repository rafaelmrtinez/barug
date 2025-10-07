from src.app.transfer_objects.request.antenatal_care_request import AntenatalCareRequest
from src.domain.contracts.antenatal_care_repository import IAntenatalCareRepository
from src.infra.contracts.connection_adapter import IConnectionAdapter


class AntenatalCareRepository(IAntenatalCareRepository):

    def __init__(self, context: IConnectionAdapter) -> None:
        self._context = context

    def insert_anc_visit(self, request: AntenatalCareRequest):

        raw = """SELECT * FROM insert_anc_visit_with_details(
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);"""
        params = [
            request.p_maternal_record_id,
            request.p_assessed_by_id,
            request.p_visit_date,
            request.p_trimester_stage_id,
            request.p_prev_illness,
            request.p_prev_hospitalization,
            request.p_prev_preg_complication,
            request.p_num_children_born_alive,
            request.p_num_children_living,
            request.p_num_abortion,
            request.p_num_stillbirth,
            request.p_num_large_babies,
            request.p_has_diabetes,
            request.p_prev_pregs,
            request.p_weight,
            request.p_height,
            request.p_bmi_status_id,
            request.p_newborn_plan,
            request.p_delivery_plan,
            request.p_gravida,
            request.p_para,
            request.p_is_fullterm,
            request.p_is_preterm,
            request.p_lmp,
            request.p_edc,
            request.p_lab_results,
            request.p_checklist_item_ids,
            request.p_risk_category_ids,
            request.p_tt_vaccines,
            request.p_iron_start_date,
            request.p_iron_end_date,
            request.p_deworming_date,
        ]
        return self._context.execute_query(raw, params)
