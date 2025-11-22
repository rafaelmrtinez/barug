class VitaminDomainException(Exception):
    """Domain-level exception for Vitamin A validation errors.

    Messages raised here are intended to be user-friendly and safe to
    surface at the API layer.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
