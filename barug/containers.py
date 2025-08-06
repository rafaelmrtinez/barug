from src.app.bootstrap.app_containers import AppContainer
from src.infra.adapter.supabase_adapter import SupabaseAdapter
from src.infra.bootstrap.infra_containers import InfraContainer
from django.conf import settings
from supabase_client_dev import supabase

infra = InfraContainer()

infra.config.from_dict({
    'AI_API_KEY': settings.AI_API_KEY,
    'AI_MODEL': settings.AI_MODEL,
    'HF_PROVIDER': settings.HF_PROVIDER,
    'HF_API_KEY': settings.HF_API_KEY,
    'HF_MODEL': settings.HF_MODEL,
    'HF_URL': settings.HF_URL
})

infra.supabase_adapter.override(SupabaseAdapter(client=supabase))

app = AppContainer(infra=infra)

app.wire(modules=[
    'ai.views',
    'faq_ingestion.views',
])