from dataclasses import dataclass

@dataclass
class DateOfBirth:
    date_of_birth: str

    def is_legal_age(self) -> bool:
        if self.years > 18:
            return True
        elif self.years == 18:
            if self.months > 0:
                return True
            elif self.months == 0:
                if self.days >= 0:
                    return True
        return False
