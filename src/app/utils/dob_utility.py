from datetime import datetime, date
from dateutil.relativedelta import relativedelta

class DateOfBirthUtility:
    
    @staticmethod
    def calculate_exact_age(dob_str: str) -> int:
        """Calculate the exact age of a person given their date of birth.

        Args:
            dob_str (str): The date of birth in the format YYYY-MM-DD.

        Raises:
            ValueError: If the date of birth is in the future or if the format is incorrect.

        Returns:
            int: The exact age in years.
        """
        try:
            dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
            today = date.today()
            if dob > today:
                raise ValueError("Date of birth cannot be in the future.")
            diff = relativedelta(today, dob)
            return diff.years
        except ValueError as e:
            return str(e)
        
    @staticmethod
    def calculate_complete_age(dob_str: str) -> tuple:
        """Calculate the complete age of a person given their date of birth.

        Args:
            dob_str (str): The date of birth in the format YYYY-MM-DD.

        Raises:
            ValueError: If the date of birth is in the future or if the format is incorrect.

        Returns:
            tuple: A tuple containing the years, months, and days of the person's age.
        """
        try:
            dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
            today = date.today()
            if dob > today:
                raise ValueError("Date of birth cannot be in the future.")
            diff = relativedelta(today, dob)
            return diff.years, diff.months, diff.days
        except ValueError as e:
            return str(e)
