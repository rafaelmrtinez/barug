from datetime import datetime, date
import math
from typing import Optional, Tuple


class AgeCalculator:
    """Utility for computing age values from dates.

    Methods are pure and accept either date/datetime or string values (ISO
    or common formats). The class provides both whole-year age (int) and a
    readable form useful for infants (months/days).
    """

    DOB_KEYS = ("date_of_birth", "dob", "birth_date")
    COMMON_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y")
    
    @staticmethod
    def float_age_to_years_months(age_float):
        """
        Converts a floating-point age in years (e.g., 44.17) 
        to a string representation of years and months.
        """
        # Extract the integer part for years (this truncates/rounds down)
        years = math.floor(age_float)
        
        # Extract the decimal part representing the fraction of the year
        decimal_part = age_float - years
        
        # Convert the decimal part to months (approx 12 months per year)
        # The result is rounded to the nearest whole month
        months = round(decimal_part * 12)
        
        # Handle cases where rounding up to 12 months occurs
        if months == 12:
            years += 1
            months = 0

        return f"{years} years and {months} months"

    @staticmethod
    def float_age_to_years(age_float) -> int:
        """Return the whole-year component (integer years) of a float age.

        Example: 4.83 -> 4
        Safely handles None and non-numeric inputs by returning 0.
        """
        try:
            if age_float is None:
                return 0
            return math.floor(float(age_float))
        except Exception:
            return 0

    @staticmethod
    def float_age_to_months(age_float) -> int:
        """Return the remaining months (0-11) part of a float age.

        Example: 4.83 -> 10 (since .83 * 12 ~= 10)
        If rounding results in 12 months, this method returns 0 (the caller
        can combine with `float_age_to_years` to account for the extra year).
        Safely handles None and non-numeric inputs by returning 0.
        """
        try:
            if age_float is None:
                return 0
            af = float(age_float)
            years = math.floor(af)
            months = round((af - years) * 12)
            if months == 12:
                return 0
            return int(months)
        except Exception:
            return 0

    @staticmethod
    def parse_date(value) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, (datetime, date)):
            # normalize to datetime
            if isinstance(value, date) and not isinstance(value, datetime):
                return datetime(value.year, value.month, value.day)
            return value
        s = str(value).strip()
        # try ISO first
        try:
            return datetime.fromisoformat(s)
        except Exception:
            pass
        for fmt in AgeCalculator.COMMON_FORMATS:
            try:
                return datetime.strptime(s, fmt)
            except Exception:
                continue
        return None

    @staticmethod
    def compute_components(dob: datetime, ref: Optional[datetime] = None) -> Tuple[int, int, int]:
        """Return (years, months, days) difference between dob and ref.

        Years is whole completed years. Months is remaining completed months
        after removing years. Days is remaining days.
        """
        if dob is None:
            return (0, 0, 0)
        ref_dt = ref or datetime.now()
        # normalize to dates to avoid DST/time issues
        d1 = date(dob.year, dob.month, dob.day)
        d2 = date(ref_dt.year, ref_dt.month, ref_dt.day)

        # compute years
        years = d2.year - d1.year
        months = d2.month - d1.month
        days = d2.day - d1.day

        if days < 0:
            # borrow days from previous month
            from calendar import monthrange

            prev_month = (d2.month - 1) or 12
            prev_year = d2.year if d2.month != 1 else d2.year - 1
            days_in_prev = monthrange(prev_year, prev_month)[1]
            days += days_in_prev
            months -= 1

        if months < 0:
            months += 12
            years -= 1

        if years < 0:
            # future DOB? clamp to zero
            return (0, 0, 0)

        return (years, months, days)

    @staticmethod
    def get_age_years_from_payload(payload: dict, ref: Optional[datetime] = None) -> int:
        """Return whole completed years for patient payload.

        Looks for common DOB keys; falls back to 'age' field when DOB missing.
        """
        for k in AgeCalculator.DOB_KEYS:
            if payload.get(k):
                dob = AgeCalculator.parse_date(payload.get(k))
                if dob:
                    years, _m, _d = AgeCalculator.compute_components(dob, ref)
                    return years
        # fallback to provided age (attempt cast)
        a = payload.get("age")
        try:
            return int(a) if a is not None else 0
        except Exception:
            return 0

    @staticmethod
    def get_readable_age_from_payload(payload: dict, ref: Optional[datetime] = None) -> str:
        """Return a readable age string: 'X years' or 'Y months' or 'Z days'.

        Useful for infants where showing months is preferable.
        """
        for k in AgeCalculator.DOB_KEYS:
            if payload.get(k):
                dob = AgeCalculator.parse_date(payload.get(k))
                if dob:
                    years, months, days = AgeCalculator.compute_components(dob, ref)
                    if years >= 1:
                        return f"{years}"
                    if months >= 1:
                        return f"{months} months"
                    return f"{days} days"
        # fallback to provided age
        a = payload.get("age")
        try:
            return str(int(a)) if a is not None else ""
        except Exception:
            return str(a) if a is not None else ""
