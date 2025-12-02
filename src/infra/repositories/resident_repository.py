from src.infra.contracts.connection_adapter import IConnectionAdapter
from src.infra.exceptions.query_exec_exception import QueryExecutionException
from typing import Optional

from src.app.transfer_objects.dto.resident_dto import (
    ResidetDTO,
    ResidentDetailDTO,
)
from src.domain.contracts.resident_repository_contract import (
    IResidentRepository,
)

class ResidentRepository(IResidentRepository):
    def __init__(self, ctx: IConnectionAdapter):
        self._ctx = ctx

    def fetch_resident_list(self) -> list[ResidetDTO]:
        query = """
            SELECT
            p.person_id,
            p.person_code,
            CONCAT_WS(' ',
                NULLIF(p.last_name, ''),
                NULLIF(p.first_name, ''),
                NULLIF(p.middle_name, ''),
                NULLIF(p.suffix, '')
            ) AS full_name,
            CONCAT_WS(', ',
                NULLIF(a.street, ''),
                NULLIF(ps.purok_sitio_name, ''),
                NULLIF(a.barangay, ''),
                NULLIF(a.city, '')
            ) AS address,
            p.mobile_num AS mob_num,
            p.email
            FROM public.person p
            LEFT JOIN public.addresss a
            ON a.address_id = p.address_id
            LEFT JOIN public.purok_sitio ps
            ON ps.purok_sitio_id = a.purok_sitio_id
            JOIN public.residential_status rs
            ON rs.residential_status_id = p.residential_status_id
            WHERE UPPER(rs.residential_status_name) = 'RESIDENT'
            ORDER BY
            UPPER(NULLIF(p.last_name, '')),
            UPPER(NULLIF(p.first_name, '')),
            UPPER(NULLIF(p.middle_name, '')),
            UPPER(NULLIF(p.suffix, ''));
        """

        try:
            rows = self._ctx.execute_query_to_dict(query, [])

            return [ResidetDTO(**row) for row in rows]
        except Exception as e:
            raise QueryExecutionException(f"Failed to fetch resident list: {str(e)}") from e
        
    def search_resident(self, search: str) -> list[ResidetDTO]:
        try:
            query = "SELECT * FROM search_residents_by_name_ilike(%s)"
            rows = self._ctx.execute_query_to_dict(query, [search])

            return [ResidetDTO(**row) for row in rows]
        except Exception as e:
            raise QueryExecutionException(f"Failed to search resident: {str(e)}") from e    
        
    def sort_purok(self, purok: int) -> list[ResidetDTO]:
        try:
            query = "SELECT * FROM filter_by_purok(%s)"
            rows = self._ctx.execute_query_to_dict(query, [purok])
            return [ResidetDTO(**row) for row in rows]
        except Exception as e:
            raise QueryExecutionException(f"Failed to sort residents by purok: {str(e)}") from e

    def fetch_resident_detail(self, person_id: int) -> Optional[ResidentDetailDTO]:
        """
        Calls the RPC function get_specific_resident_full_profile to retrieve
        comprehensive resident details.
        """
        try:
            sql = """
                SELECT * FROM public.get_specific_resident_full_profile(%s);
            """
            rows = self._ctx.execute_query_to_dict(sql, [person_id])
            
            if not rows:
                return None
            
            row = rows[0]
            
            # Convert arrays to lists if they exist
            government_programs = row.get('government_programs') or []
            other_family_members = row.get('other_family_members') or []
            children_ids = row.get('children_ids') or []
            children_names = row.get('children_names') or []
            
            return ResidentDetailDTO(
                person_id=row.get('person_id'),
                person_code=row.get('person_code') or '',
                first_name=row.get('first_name') or '',
                middle_name=row.get('middle_name'),
                last_name=row.get('last_name') or '',
                suffix=row.get('suffix'),
                birthdate=row.get('birthdate'),
                email=row.get('email'),
                mobile_num=row.get('mobile_num'),
                sex=row.get('sex'),
                age=row.get('age'),
                civil_status=row.get('civil_status'),
                address_id=row.get('address_id'),
                street_name=row.get('street_name'),
                purok_sitio_name=row.get('purok_sitio_name'),
                barangay_name=row.get('barangay_name'),
                city_name=row.get('city_name'),
                religion=row.get('religion'),
                nationality=row.get('nationality'),
                education=row.get('education'),
                employment_status=row.get('employment_status'),
                occupation=row.get('occupation'),
                government_programs=government_programs,
                residential_status=row.get('residential_status'),
                residency_period=row.get('residency_period'),
                resident_since=row.get('resident_since'),
                date_added=row.get('date_added'),
                is_email_verified=row.get('is_email_verified'),
                is_business_owner=row.get('is_business_owner'),
                is_id_valid=row.get('is_id_valid'),
                is_student=row.get('is_student'),
                personal_monthly_income=row.get('personal_monthly_income'),
                valid_id_front_path=row.get('valid_id_front_path'),
                valid_id_back_path=row.get('valid_id_back_path'),
                id_type_name=row.get('id_type_name'),
                selfie_with_id=row.get('selfie_with_id'),
                profile_picture=row.get('profile_picture'),
                registration_method=row.get('registration_method'),
                household_head_first_name=row.get('household_head_first_name'),
                household_head_middle_name=row.get('household_head_middle_name'),
                household_head_last_name=row.get('household_head_last_name'),
                household_head_suffix=row.get('household_head_suffix'),
                household_num=row.get('household_num'),
                house_type=row.get('house_type'),
                house_ownership=row.get('house_ownership'),
                family_head_first_name=row.get('family_head_first_name'),
                family_head_middle_name=row.get('family_head_middle_name'),
                family_head_last_name=row.get('family_head_last_name'),
                family_head_suffix=row.get('family_head_suffix'),
                family_num=row.get('family_num'),
                household_type=row.get('household_type'),
                nhts_status=row.get('nhts_status'),
                indigent_status=row.get('indigent_status'),
                source_of_income=row.get('source_of_income'),
                family_monthly_income=row.get('family_monthly_income'),
                other_family_members=other_family_members,
                is_staff=row.get('is_staff'),
                staff_id=row.get('staff_id'),
                role_name=row.get('role_name'),
                supabase_uid=row.get('supabase_uid'),
                mother_id=row.get('mother_id'),
                mother_name=row.get('mother_name'),
                father_id=row.get('father_id'),
                father_name=row.get('father_name'),
                guardian_id=row.get('guardian_id'),
                guardian_name=row.get('guardian_name'),
                children_ids=children_ids,
                children_names=children_names,
            )
            
        except Exception as e:
            raise QueryExecutionException(f"fetch_resident_detail failed: {e}", "E_DB") from e
