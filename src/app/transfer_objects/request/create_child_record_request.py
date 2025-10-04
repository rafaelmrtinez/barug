from dataclasses import dataclass


@dataclass
class CreateChildRecordRequest:
    p_staff_id: int
    p_person_id: int
    p_mother_id: int
    p_father_id: int
    p_birth_order: str
    p_delivery_place_type_id: int
    p_family_id: int