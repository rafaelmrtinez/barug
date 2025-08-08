from django.test import TestCase


# Create your tests here.
class FaqIngestionPipelineTestCase(TestCase):
    
    def batch_embedding_generation_test_helper(self, bulk_data: list, batch_size: int) -> list:
        for i in range(0, len(bulk_data), batch_size):
            yield bulk_data[i:i + batch_size]
            
    def test_batch_embedding_generation(self):
        BATCH_SIZE = 50
        
        container = []
        
        for i in range(100):
            container.append([i])

        embeddings = []
        
        for batch in self.batch_embedding_generation_test_helper(bulk_data=container, batch_size=BATCH_SIZE):
            print(f"Processing batch: {batch}\n\n")
            embeddings.extend(batch)
            
        print(f"Total embeddings generated: {len(embeddings)}\n\n")
        print(embeddings)