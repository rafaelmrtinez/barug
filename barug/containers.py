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
    "child_health.api.child_health_schedule_api",
    # maternal API endpoints that require application services (dependency-injected)
    "maternal.api.complete_maternal_visit_api",
    "maternal.api.download_image_download_api",
    "maternal.api.insert_postpartum_record_api",
    "maternal.api.risk_codes_api",
    "maternal.api.insert_postpartum_schedule_api",
    "maternal.api.insert_prenatal_schedule_api",
    "maternal.api.maternal_heal_status_api",
    "maternal.api.medical_history_api",
    "maternal.api.previous_pregnancy_api",
    "maternal.api.checklist_api",
    "maternal.api.plans_api",
    "maternal.api.micronutrients_api",
    "maternal.api.prenatal_followup_api",
    "maternal.api.mhr_side_panel_api",
    "maternal.api.maternal_report_api",
    "maternal.api.obstetric_api",
    "maternal.api.present_pregnancy_api",
    "maternal.api.tetanus_toxoid_api",
    "doc_ingest.api.faq_ingest_api",
    # child health endpoints
    "child_health.api.newborn_screening_api",
    "child_health.api.birth_supplementation_api",
    "child_health.api.vitamin_api",
    "child_health.api.child_visit_api",
    "child_health.api.iron_intake_api",
    "child_health.api.bf_feeding_api",
    "common.api.residents_pdf_api",
    "common.api.business_pdf_api",
    "common.api.household_pdf_api",
    "captain.views",
    "clerk.views",
    "treasurer.views",
    "secretary.views",
    "lupon_mem.views",
    "lupon_pres.views",
    "staff_admin.views",
])