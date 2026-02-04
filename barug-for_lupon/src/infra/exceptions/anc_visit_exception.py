class ANCVisitException(Exception):
    
    ERROR_CODES = ['P6060', 'P6057', 'P6061', 'P6062', 'P6063', 'P6064', 'P6065', 'P6066'];
    
    def __init__(self, message: str):
        self.message = message
        
    
    @classmethod
    def is_anc_visit_exception(cls, code: int) -> bool:
        return code in cls.ERROR_CODES