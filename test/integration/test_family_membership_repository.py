from django.test import TestCase


from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.infra.repository.family_membership_repositroy import FamilyMembershipRepository


from supabase_client import supabase


class FamilyMembershipRepositoryTestCase(TestCase):
    
    def setUp(self):
        self.repository = FamilyMembershipRepository(
            client=SupabaseAdapter(
                client=supabase
            )
        )
        
    def test_join_family_unit(self):
        self.repository.join_family_unit(
            {
                'p_requester_id': 187,
                'p_family_id': 1,
                'p_relationship_to_hholdhead_id': 1,
                'p_relationship_to_family_head_id': 1,
                'p_residency_period': 10
            }
        )