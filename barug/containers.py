from src.app.bootstrap.app_containers import AppContainer
from django.conf import settings

from src.infra.bootstrap.app_containers import InfraContainer


infra = InfraContainer()

infra.config.from_dict({})


app = AppContainer(infra=infra)

app.wire(modules=[])