from dependency_injector import containers, providers



from src.core.contracts.infra.family_membership import IFamilyMembershipRepository
from src.core.contracts.infra.repository.family_creation import IFamilyCreationRepository
from src.core.contracts.infra.repository.household_creation import IHouseholdCreationRepository
from src.core.contracts.infra.repository.household_search_repository import IHouseholdSearchRepository
from src.core.contracts.infra.repository.resident_repository import IResidentRepository
from src.core.contracts.llm import ILLM
from src.core.contracts.embedding import IEmbedding
from src.infra.gateways.groq_client import GroqClient
from src.core.contracts.rag_repository import IRAGRepository
from src.infra.gateways.hf_embedding import HuggingFaceClient
from src.infra.repository.family_creation_repository import FamilyCreationRepository
from src.infra.repository.family_membership_repositroy import FamilyMembershipRepository
from src.infra.repository.household_creation_repository import HouseholdCreationRepository
from src.infra.repository.household_search_repository import HouseholdSearchRepository
from src.infra.repository.rag_repository import RAGRepository
from src.core.contracts.faq_repo import IFAQIngestionRepository
from src.infra.repository.faq_ingestion_repository import FAQIngestionRepository
from src.infra.repository.resident_repository import ResidentRepository


class InfraContainer(containers.DeclarativeContainer):

    config = providers.Configuration()

    supabase_adapter_dev = providers.Object(None)
    database = providers.Object(None)
    
    resident_repository: providers.Factory[IResidentRepository] = providers.Factory(
        ResidentRepository,
        client=database
    )
    
    household_creation_repository: providers.Factory[IHouseholdCreationRepository] = providers.Factory(
        HouseholdCreationRepository,
        client=database
    )
    
    family_creation_repository: providers.Factory[IFamilyCreationRepository] = providers.Factory(
        FamilyCreationRepository,
        client=database
    )

    household_search_repository : providers.Factory[IHouseholdSearchRepository] = providers.Factory(
        HouseholdSearchRepository,
        client=database
    )
    
    family_membership_repository : providers.Factory[IFamilyMembershipRepository] = providers.Factory(
        FamilyMembershipRepository,
        client=database
    )
    
    faq_entries_repository: providers.Factory[IFAQIngestionRepository] = providers.Factory(
        FAQIngestionRepository,
        supabase_adapter=supabase_adapter_dev
    )

    rag_repository: providers.Factory[IRAGRepository] = providers.Factory(
        RAGRepository,
        supabase_adapter=supabase_adapter_dev,
    )

    embedding: providers.Singleton[IEmbedding] = providers.Singleton(
        HuggingFaceClient,
        provider=config.EMBEDDING_PROVIDER,
        api_key=config.EMBEDDING_API_KEY,
        model=config.EMBEDDING_MODEL,
        url=config.EMBEDDING_URL
    )

    llm_client: providers.Singleton[ILLM] = providers.Singleton(
        GroqClient,
        api_key=config.AI_API_KEY,
        model=config.AI_MODEL
    )
