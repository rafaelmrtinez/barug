from django.test import TestCase
from django.conf import settings

from src.core.contracts.embedding import IEmbedding
from src.infra.bootstrap.infra_containers import InfraContainer
from dependency_injector.wiring import inject, Provide

# Create your tests here.
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
        
        print(f"Generated embedding for '{text}': {embedding}")
        
        self.assertIsInstance(embedding, list)
        self.assertGreater(len(embedding), 0)