from pydantic import BaseModel
import decimal
import datetime as date

class ChildMonitoringLog(BaseModel):
    date: date.date
    age: decimal.Decimal
    weight: decimal.Decimal
    temp: decimal.Decimal
    height: decimal.Decimal
    findings: str | None = None
    notes: str | None = None
    
    def __init__(self, **data):
        if 'age' in data:
            data['age'] = decimal.Decimal(data['age'])
        if 'weight' in data:
            data['weight'] = decimal.Decimal(data['weight'])
        if 'temp' in data:
            data['temp'] = decimal.Decimal(data['temp'])
        if 'height' in data:
            data['height'] = decimal.Decimal(data['height'])
        super().__init__(**data)