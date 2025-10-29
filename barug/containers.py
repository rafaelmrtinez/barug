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
    "captain.views",
    "clerk.views",
    "secretary.views",
])