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

    @staticmethod
    def to_date(value) -> date | None:
        """Normalize value to a date object.

        Accepts a `datetime.date` or an ISO date string and returns a `date` or None.
        """
        if value is None:
            return None
        if isinstance(value, date):
            return value
        # allow numeric or other types by converting to str then parsing
        return DateAndTimeUtility.parse_date(str(value))