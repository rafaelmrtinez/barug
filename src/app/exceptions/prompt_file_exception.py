class PromptFileException(FileNotFoundError):
    """Custom exception for handling prompt file errors."""
    
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self):
        return f"PromptFileException: {self.message}"