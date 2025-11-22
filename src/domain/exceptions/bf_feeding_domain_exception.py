from src.domain.exceptions.child_health_domain_exception import ChildHealthDomainException


class BfFeedingDomainException(ChildHealthDomainException):
    """Domain exception for breastfeeding feeding business rules."""

    def __init__(self, message: str):
        super().__init__(message)
