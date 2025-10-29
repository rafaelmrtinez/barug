class PersonNotFoundException(Exception):
    
    def __init__(self, person_id: int):
        self.person_id = person_id