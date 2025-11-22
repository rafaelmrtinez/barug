class ChildVisitDomainException(Exception):
    """Domain-level exception for child visit validation errors.

    Carries a user-friendly message and optional machine code.
    """

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
