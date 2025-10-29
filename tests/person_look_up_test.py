from django.test import TestCase

from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.maternal_repository import MaternalRepository


class PersonLookUpTest(TestCase):
    
    def setUp(self):
        self.repo = MaternalRepository(
            ctx=ConnectionAdapter()
        )
        
    def test_get_child_record_by_person_id(self):
        id = self.repo.get_child_record_by_person_id(person_id=181)
        print(f"Record found with record id: {id}")
        self.assertIsInstance(id, int)