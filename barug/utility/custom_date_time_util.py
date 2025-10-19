from datetime import datetime
import pytz


class DateAndTimeUtility:
    
    TIME_ZONE = "Asia/Manila"
    
    @staticmethod
    def get_current_date():
        ph_tz = pytz.timezone(DateAndTimeUtility.TIME_ZONE)
        ph_date = datetime.now(ph_tz)
        return ph_date.strftime("%Y-%m-%d")