from src.app.transfer_objects.request.anc_labolatory_results_request import ANCLaboratoryResultsRequest
from src.app.transfer_objects.request.tetanus_toxoid_request import TetanusToxoidRequest


class ANCViewUtility:
    
    @staticmethod
    def laboratory_results_obj_converter(obj: dict) -> None | ANCLaboratoryResultsRequest:
        list_of_results = []
        print(f'Converting laboratory results... {obj}')
        for i in obj:
            list_of_results.append(ANCLaboratoryResultsRequest(
                lab_test_id=i.get("type", None),
                result=i.get("result", None),
                date_tested=i.get("date", None)
            ))
        return list_of_results if list_of_results else None
    
    @staticmethod
    def match_those_tities(tits) -> None | list[TetanusToxoidRequest]:
        list_of_tities = []
        for i in tits:
            list_of_tities.append(
                TetanusToxoidRequest(
                    tt_type_id=i.get("dose", None),
                    date_given=i.get("date", None)
                )
            )
        return list_of_tities if list_of_tities else None