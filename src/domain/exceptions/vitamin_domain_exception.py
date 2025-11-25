class VitaminDomainException(Exception):
    """Domain-level exception for Vitamin A validation errors.

    Carries a user-facing message and an optional machine-friendly code
    suitable for telemetry or automated handling.
    """

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
