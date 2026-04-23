from datetime import date
from typing import Literal
from pydantic import BaseModel, field_validator

class TetanusToxoidRequest(BaseModel):
    tt_type_id: int | str | None = None
    date_given: date | None = None
    
    
    @field_validator("tt_type_id", mode="before")
    @classmethod
    def map_ids(cls, v: int | str | None) -> None | Literal[1] | Literal[2] | Literal[3] | Literal[4] | Literal[5] | Literal[6]:
        if v == "TT1":
            return 1
        elif v == "TT2":
            return 2
        elif v == "TT3":
            return 3
        elif v == "TT4":
            return 4
        elif v == "TT5":
            return 5
        elif v == "FIM":
            return 6
        return None