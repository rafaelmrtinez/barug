class IdentificationGenerator:

    @staticmethod
    def generate_family_number(household_id: str, family_count: int) -> str:
        return f"HH{household_id}-FAM00{family_count + 1}"

    @staticmethod
    def generate_household_number(household_id: int, family_count: int) -> str:
        # return f"HH{household_id}-FAM00{family_count + 1}"
        pass

    @staticmethod
    def generate_ucf_number(household_id: int, total_family_count: int) -> str:
        return f"UFC-{household_id}-{total_family_count + 1}"
