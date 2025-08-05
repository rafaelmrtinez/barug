from pprint import pprint
from django.test import TestCase
from django.conf import settings

from src.app.dto.semantic_search import SemanticSearchDTO
from src.core.contracts.document_repository import IDocumentRepository
from src.core.contracts.embedding import IEmbedding
from src.infra.bootstrap.infra_containers import InfraContainer
from dependency_injector.wiring import inject, Provide
from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.infra.repository.ai_repository import AIRepository
from src.infra.repository.document_repository import DocumentRepository


# Create your tests here.
class DocumentRepositoryTestCase(TestCase):
    
    def setUp(self):
        from supabase_client_dev import supabase
        self.infra = InfraContainer()
        self.infra.config.from_dict({
            'HF_PROVIDER': settings.HF_PROVIDER,
            'HF_API_KEY': settings.HF_API_KEY,
            'HF_MODEL': settings.HF_MODEL
        })
        self.infra.supabase_adapter.override(SupabaseAdapter(client=supabase))
        self.infra.wire(modules=['ai.tests'])
        
    @inject
    def test_get_faq_document_id_order_by_date(
        self, 
        repo: (IDocumentRepository | DocumentRepository ) = Provide[InfraContainer.document_repository]) -> int:
        id = repo.get_faq_document_id_order_by_date()
        self.assertIsNotNone(id)

class RAGPipelineTestCase(TestCase):

    def setUp(self):
        self.test_data = [{'answer': 'Visit the Barangay Hall, fill out a form, present a valid ID, and '
                    'pay the fee.',
                    'id': '51e3b214-3ce1-451e-8442-59eb83a071d7',
                    'question': 'How do I request a Barangay Clearance?',
                    'similarity': 0.987718762431292},
                    {'answer': 'Valid ID, proof of residence, and sometimes community tax '
                    'certificate (cedula).',
                    'id': '0cb169c1-3147-48ec-91c7-038ccc247611',
                    'question': 'What documents are needed for a Barangay Clearance?',
                    'similarity': 0.937854321662957},
                    {'answer': 'Submit business documents and pay the corresponding barangay fee.',
                    'id': '16337766-05ea-45f7-b809-5c908da2f44e',
                    'question': 'How do I request a Barangay Permit for business?',
                    'similarity': 0.922997062027631}]
        self.test_dto = [
            SemanticSearchDTO(
                question='How do I request a Barangay Clearance?', 
                answer='Visit the Barangay Hall, fill out a form, present a valid ID, and pay the fee.'),
            SemanticSearchDTO(
                question='What documents are needed for a Barangay Clearance?', 
                answer='Valid ID, proof of residence, and sometimes community tax certificate (cedula).'),
            SemanticSearchDTO(
                question='How do I request a Barangay Permit for business?', 
                answer='Submit business documents and pay the corresponding barangay fee.')
        ]
        
    def test_extract_larger_content(self):
        # This test should confirm that the context string is written corretly within the template file.
        
        query = "How can I get a Barangay Clearance?"
        context_str = ""
        
        for i in range(len(self.test_dto)):
            context_str += f"Top {i+1} Result\n- Question: {self.test_dto[i].question}\n- Answer: {self.test_dto[i].answer}\n\n"
        # print(context_str)
        
        path = 'src/app/pipelines/prompts/prompt.txt'
        result = None
        
        with open(path, 'r') as file:
            template = file.read()
            result = template.format(query=query, context=context_str)

        # print(f"Template content: {result}")

    def test_rag_pipeline_utils_extract_top_k_content(self):
        from src.app.utils.rag_pipeline_utils import RAGPipelineUtils
        
        # This test confirm the test from the "def test_extract_top_k_content(self):" is accurate.
        
        instance = RAGPipelineUtils()
        res = instance.extract_top_k_content(self.test_data)
        # pprint(f"Extracted top-k content: {res}")
        self.assertEqual(res, self.test_dto)
        self.assertIsInstance(res, list)
        self.assertGreater(len(res), 0)
        self.assertIsInstance(res[0], SemanticSearchDTO)
        self.assertEqual(res[0].question, self.test_dto[0].question)
        self.assertEqual(res[0].answer, self.test_dto[0].answer)
        
    def test_extract_top_k_content(self):
        
        # According to my test results, these are the expected results to be extracted from the test_data.
        #
        # 
        # [
        #     SemanticSearchDTO(
        #         question='How do I request a Barangay Clearance?', 
        #         answer='Visit the Barangay Hall, fill out a form, present a valid ID, and pay the fee.'),
        #     SemanticSearchDTO(
        #         question='What documents are needed for a Barangay Clearance?', 
        #         answer='Valid ID, proof of residence, and sometimes community tax certificate (cedula).'),
        #     SemanticSearchDTO(
        #         question='How do I request a Barangay Permit for business?', 
        #         answer='Submit business documents and pay the corresponding barangay fee.')
        # ]
        
        dto_list = []
        for i in range(len(self.test_data)):
            dto_list.append(
                SemanticSearchDTO(
                    question=self.test_data[i]['question'],
                    answer=self.test_data[i]['answer']
                )
            ) 
            
        # pprint(dto_list)
        self.assertEqual(dto_list, self.test_dto)
        self.assertIsInstance(dto_list, list)
        self.assertGreater(len(dto_list), 0)
        self.assertIsInstance(dto_list[0], SemanticSearchDTO)
        self.assertEqual(dto_list[0].question, self.test_dto[0].question)
        self.assertEqual(dto_list[0].answer, self.test_dto[0].answer)
        self.assertEqual(dto_list[1].question, self.test_dto[1].question)
        self.assertEqual(dto_list[1].answer, self.test_dto[1].answer)

class AIRepositoryTestCase(TestCase):

    def setUp(self):
        from supabase_client_dev import supabase
        self.infra = InfraContainer()
        self.infra.config.from_dict({
            'HF_PROVIDER': settings.HF_PROVIDER,
            'HF_API_KEY': settings.HF_API_KEY,
            'HF_MODEL': settings.HF_MODEL
        })
        self.infra.supabase_adapter.override(SupabaseAdapter(client=supabase))
        self.infra.wire(modules=['ai.tests'])

    @inject
    def test_semantic_search(
        self,
        repo: AIRepository = Provide[InfraContainer.ai_repository],
        hf_embedding: IEmbedding = Provide[InfraContainer.hf_embedding]
    ):
        word = "how can i get barangay clearance?"
        embedding = hf_embedding.generate_embedding(word)
        sample_uuid = '51e3b214-3ce1-451e-8442-59eb83a071d7'
        top_res = repo.exec_semantic_search(
            'match_faq_entries', embedding, 0.7, 3, sample_uuid)
        # pprint(f"Generated embedding for '{word}': {embedding}")
        # pprint(f"Top results: {top_res}")


class SupabaseAdapterTestCase(TestCase):

    def setUp(self):
        from supabase_client_dev import supabase
        self.infra = InfraContainer()
        self.infra.config.from_dict({
            'HF_PROVIDER': settings.HF_PROVIDER,
            'HF_API_KEY': settings.HF_API_KEY,
            'HF_MODEL': settings.HF_MODEL
        })
        self.infra.supabase_adapter.override(SupabaseAdapter(client=supabase))
        self.infra.wire(modules=['ai.tests'])

    @inject
    def test_semantic_search(
        self,
        supa: SupabaseAdapter = Provide[InfraContainer.supabase_adapter],
        hf_embedding: IEmbedding = Provide[InfraContainer.hf_embedding]
    ):
        word = "how can i get barangay clearance?"
        embedding = hf_embedding.generate_embedding(word)
        # print(f"Generated embedding for '{word}': {embedding}")
        client = supa.get_client()

        res = client.rpc('match_faq_entries', {
            'query_embedding': embedding,
            'match_threshold': 0.7,
            'match_count': 3
        }).execute()

        # print(f"RPC response: {res}")

        # print(f"Supabase client: {client}")
        self.assertIsNotNone(client)

    @inject
    def test_get_client(self, supa: SupabaseAdapter = Provide[InfraContainer.supabase_adapter]):
        client = supa.get_client()
        # print(f"Supabase client: {client}")
        self.assertIsNotNone(client)


class HFEmbeddingTestCase(TestCase):

    def setUp(self):
        self.infra = InfraContainer()
        self.infra.config.from_dict({
            'HF_PROVIDER': settings.HF_PROVIDER,
            'HF_API_KEY': settings.HF_API_KEY,
            'HF_MODEL': settings.HF_MODEL
        })

        self.infra.wire(modules=['ai.tests'])

    @inject
    def test_generate_embedding(self, hf_embedding: IEmbedding = Provide[InfraContainer.hf_embedding]):
        text = "123"
        embedding = hf_embedding.generate_embedding(text)

        # print(f"Generated embedding for '{text}': {embedding}")

        self.assertIsInstance(embedding, list)
        self.assertGreater(len(embedding), 0)
