# utilities/immunization.py (or wherever is handy)
class ImmunizationUtility:
    # Stage IDs as used in DB:
    # 1 = WITHIN 24 HOURS, 2 = 1ST DOSE, 3 = 2ND DOSE, 4 = 3RD DOSE
    STAGES = [
        ("24hr", 1),
        ("1st",  2),
        ("2nd",  3),
        ("3rd",  4),
    ]

    # Map form field prefixes to immunization_type_id
    TYPE_MAP = {
        "bcg":         1,
        "hepbv":       2,
        "pcv":         3,
        "opv":         4,
        "amv":         5,
        "pentavalent": 6,
    }

    @staticmethod
    def most_recent_per_type(cleaned_data):
        """
        From cleaned_data, return a list of (type_id, stage_id, date_given),
        choosing only the highest stage that has a date for each type.
        """
        results = []
        for prefix, type_id in ImmunizationUtility.TYPE_MAP.items():
            # check stages from newest -> oldest (3rd, 2nd, 1st, 24hr)
            for stage_name, stage_id in reversed(ImmunizationUtility.STAGES):
                field = f"{prefix}_{stage_name}"
                dt = cleaned_data.get(field)
                if dt:
                    results.append((type_id, stage_id, dt))
                    break  # only the most-recent per type
        return results
