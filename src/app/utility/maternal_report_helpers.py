from typing import Optional
import os


class MaternalReportHelpers:
    """Small container of static helper functions extracted from inner scope.

    These utilities are pure functions and are safe to call from the
    service. Keeping them as static methods makes them easy to test and
    avoids recreating them on each invocation of the service.
    """

    @staticmethod
    def bool_to_yesno(val) -> str:
        if val is True or str(val).lower() == "true":
            return "Yes"
        if val is False or str(val).lower() == "false":
            return "No"
        return str(val) if val is not None else ""

    @staticmethod
    def compute_bmi(weight_val, height_val) -> Optional[str]:
        try:
            if weight_val is None or height_val is None:
                return None
            w = float(weight_val)
            h = float(height_val)
            if h > 3:
                h = h / 100.0
            if h <= 0:
                return None
            bmi = w / (h * h)
            return f"{bmi:.1f}"
        except Exception:
            return None

    @staticmethod
    def resolve_image(path_val: Optional[str]) -> Optional[str]:
        if not path_val:
            return None
        # if absolute path and exists, use it
        if os.path.isabs(path_val) and os.path.exists(path_val):
            return path_val
        # last resort: try the value as-is (relative to cwd or URL)
        return path_val if os.path.exists(path_val) else None
