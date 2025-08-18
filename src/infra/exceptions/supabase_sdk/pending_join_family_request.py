class PendingFamilyRequestException(Exception):
    """Exception raised when there is a pending family request."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)