class QueryExecutionException(Exception):
    
    def __init__(self, message: str, code: int):
        super().__init__(message, code)
        self.message = message
        self.code = code