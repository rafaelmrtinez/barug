from dataclasses import dataclass


@dataclass(frozen=True)
class HouseholdCreationPersistence:
    p_requester_id: int
    p_household_num: str
    p_house_number: str
    p_household_req_desc: str
    p_house_type_id: int
    p_house_ownership_id: int
    p_city: int
    p_barangay: str
    p_sitio_purok: str
    p_street: str
    p_is_hhold_head: bool
