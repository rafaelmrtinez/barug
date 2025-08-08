from src.app.bootstrap.app_containers import AppContainer
from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.infra.bootstrap.infra_containers import InfraContainer
from django.conf import settings
from supabase_client_dev import supabase

infra = InfraContainer()

infra.config.from_dict({
    'AI_API_KEY': settings.AI_API_KEY,
    'AI_MODEL': settings.AI_MODEL,
    'EMBEDDING_PROVIDER': settings.EMBEDDING_PROVIDER,
    'EMBEDDING_API_KEY': settings.EMBEDDING_API_KEY,
    'EMBEDDING_MODEL': settings.EMBEDDING_MODEL,
    'EMBEDDING_URL': settings.EMBEDDING_URL
})

infra.supabase_adapter.override(SupabaseAdapter(client=supabase))

app = AppContainer(infra=infra)

app.wire(modules=[
    'ai.views',
    'faq_ingestion.views',
])