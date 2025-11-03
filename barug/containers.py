from src.app.bootstrap.app_containers import AppContainer
from django.conf import settings

from src.infra.bootstrap.infrastructure_containers import InfraContainer
from src.infra.database.connection_adapter import ConnectionAdapter


infra = InfraContainer()

infra.config.from_dict({})
infra.context.override(ConnectionAdapter())


app = AppContainer(infra=infra)

app.wire(modules=[
    "bhw.views",
    "midwife.views",
    # maternal API endpoints that require application services (dependency-injected)
    "maternal.api.complete_maternal_visit_api",
    "maternal.api.download_image_download_api",
    "maternal.api.insert_postpartum_record_api",
    "maternal.api.insert_postpartum_schedule_api",
    "maternal.api.insert_prenatal_schedule_api",
    "maternal.api.maternal_heal_status_api",
    "maternal.api.mhr_side_panel_api",
    "maternal.api.maternal_report_api",
    "doc_ingest.api.faq_ingest_api",
    "captain.views",
    "clerk.views",
    "secretary.views",
])