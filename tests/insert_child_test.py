from django.test import TestCase

from src.app.transfer_objects.request.create_child_record_request import CreateChildRecordRequest
from src.infra.database.connection_adapter import ConnectionAdapter
from src.infra.repositories.maternal_repository import MaternalRepository


class InsertChildTest(TestCase):
    
    def setUp(self):
        self._ctx = MaternalRepository(ConnectionAdapter())
        
    def test_insert_child(self):
        request = CreateChildRecordRequest(
            p_staff_id=1,
            p_person_id=12345,
            p_mother_id=1,
            p_father_id=2,
            p_birth_order="1",
            p_delivery_place_type_id=1,
            p_family_id=1
        )
        result = self._ctx.insert_child_record(request)
        print(result)
        self.assertIsInstance(result, int)
        self.assertGreater(result, 0)