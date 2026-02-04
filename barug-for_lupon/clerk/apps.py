from django.apps import AppConfig


class ClerkConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'clerk'

    # def ready(self):
    #     from src.app.bootstrap.app_containers import AppContainer
    #     from src.infra.bootstrap.infrastructure_containers import InfraContainer  # your infra container

    #     container = AppContainer()
    #     infra = InfraContainer()
    #     container.infra.override(infra)

    #     # This uses wiring_config, but you can be explicit too:
    #     container.wire(modules=["clerk.views.business"])