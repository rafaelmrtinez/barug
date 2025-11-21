from src.domain.exceptions.child_health_domain_exception import ChildHealthDomainException


class NewbornScreeningDomainException(ChildHealthDomainException):
    """Domain-specific exception for newborn screening business rule violations."""

    def __init__(self, message: str):
        super().__init__(message)
