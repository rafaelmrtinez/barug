class ChildHealthRecordException(Exception):
    """Base exception for child health record/report operations."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
