from datetime import date, datetime
import pytz


class DateAndTimeUtility:
    
    TIME_ZONE = "Asia/Manila"
    
    @staticmethod
    def get_current_date():
        ph_tz = pytz.timezone(DateAndTimeUtility.TIME_ZONE)
        ph_date = datetime.now(ph_tz)
        return ph_date.strftime("%Y-%m-%d")
    
    @staticmethod
    def parse_date(value) -> date | None:
        """
        Helper: parse ISO date (yyyy-mm-dd)

        Args:
            value (str): The date string to parse.

        Returns:
            _type_: _Date | None: Parsed date or None if invalid. 
        """
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None