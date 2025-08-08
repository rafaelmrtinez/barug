class DataAccessException(Exception):
    """
    Exception raised for errors in data access operations.
    
    Attributes:
        message -- explanation of the error
    """
    
    def __init__(self, message="An error occurred while accessing data."):
        self.message = message
        super().__init__(self.message)
    
    def __str__(self):
        return f"DataAccessException: {self.message}"