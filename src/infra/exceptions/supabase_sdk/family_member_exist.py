class FamilyMemberAlreadyExistException(Exception):
    """Exception raised when a family member already exists."""
    
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)