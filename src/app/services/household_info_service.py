from src.infra.repositories.household_info_repository import HouseholdInfoRepository


class HouseholdInformationService:
    
    def __init__(self, household_info_repository: HouseholdInfoRepository):
        self._household_info_repository = household_info_repository
        
    def execute(self, household_id: int):
        basic_household_info = self._household_info_repository.get_basic_info_by_id(household_id)
        raw_families = self._household_info_repository.get_basic_family_unit_details_by_household_id(household_id)
        normalized_families = []
        for f in raw_families:
            member_names = [
                m["name"].strip()
                for m in f.get("members", [])
                if m and m.get("name") and m["name"].strip()
            ]
            
            normalized_families.append({
                "family_id": f["family_id"],
                "family_num": f["family_num"],
                "head_name": f.get("family_head", "").strip(),
                "type": f.get("household_type_name", ""),
                "nhts": f.get("nhts_status_name", ""),
                "indigent": f.get("indigent_status_name", ""),
                "monthly_income": f.get("income_range_amnt", ""),
                "source_income": f.get("source_of_income", ""),
                "members": member_names,
                "member_details": f.get("members", []),
            })
        return {
            "household_info": basic_household_info,
            "family_units": normalized_families,
        }