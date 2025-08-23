from datetime import datetime, date
from dateutil.relativedelta import relativedelta

class DateOfBirthUtility:
    
    @staticmethod
    def calculate_exact_age(dob_str: str):
        try:
            dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
            today = date.today()
            if dob > today:
                raise ValueError("Date of birth cannot be in the future.")
            diff = relativedelta(today, dob)
            return diff.years, diff.months, diff.days
        except ValueError as e:
            return str(e)
