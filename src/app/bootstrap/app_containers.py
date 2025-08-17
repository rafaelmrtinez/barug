from dependency_injector import containers, providers


from src.app.pipelines.rag_pipeline import RAGPipeline
from src.core.contracts.app.family_service import IFamilyMembershipService
from src.core.contracts.app.pipeline import IPipeline
from src.app.services.family_membership import FamilyMembershipService
from src.app.pipelines.faq_ingestion_pipeline import FAQIngestionPipeline


class AppContainer(containers.DeclarativeContainer):
    """Application container for dependency injection."""
    
    config = providers.Configuration()
    
    infra  = providers.DependenciesContainer()
    
    family_membership: providers.Factory[
        IFamilyMembershipService
        ] = providers.Factory(
        FamilyMembershipService,
        repository=infra.family_membership_repository
    )
    
    faq_ingestion_pipeline: providers.Factory[IPipeline] = providers.Factory(
        FAQIngestionPipeline,
        faq_entry_repo=infra.faq_entries_repository ,
        embedding=infra.embedding
    )
    
    rag_pipeline: providers.Factory[IPipeline] = providers.Factory(
        RAGPipeline,
        repos=infra.rag_repository,
        embedding=infra.embedding,
        llm=infra.llm_client,
    )