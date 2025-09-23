from dependency_injector import containers, providers


class InfraContainer(containers.DeclarativeContainer):

    config = providers.Configuration()
    supabase_adapter_dev = providers.Object(None)
    database = providers.Object(None)