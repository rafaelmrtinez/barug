from dataclasses import dataclass

@dataclass(frozen=True)
class Money:
    """
    This value object is used to enforce business rules
    for Money.
    """

    amount: float
    currency: str = "Php"

    def __post_init__(self):
        if self.amount < 0:
            raise ValueError("Amount cannot be negative.")
        
        if not self.currency or len(self.currency) != 3:
            raise ValueError("Currency must be a valid 3-letter code.")