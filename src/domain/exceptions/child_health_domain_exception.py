class ChildHealthDomainException(Exception):
    """Base exception for child health domain errors."""
    
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)