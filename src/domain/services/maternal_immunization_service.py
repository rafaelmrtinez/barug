class MaternalDomainService:

    @staticmethod
    def determine_latest_immunization(immunization):
        key = "pentavalent" if immunization.name == "penta" else (
            "hep bv" if immunization.name == "hepb" else immunization.name)

        doses = [immunization.d0, immunization.d1,
                 immunization.d2, immunization.d3]
        for stage, dose_date in reversed(list(enumerate(doses, start=1))):
            if dose_date:
                return key.upper(), dose_date, stage
        return None

    @staticmethod
    def __check_record_naming(record: str) -> bool:
        return "PENTAVALENT" if record.upper() == "PENTA" else record.upper()

    @staticmethod
    def validate_immunization_sequence(immunization_data):
        """
        Validates the immunization sequence for the given data.
        Ensures that doses are given in the correct order without skipping any.

        Hierarchy of Prescription:
            \n- d0 must be given before d1
            \n- d1 must be given before d2
            \n- d2 must be given before d3

        Args:
            immunization_data (list): A list of immunization records, each containing dose information.

        Returns:
            list: A list of error messages, if any.
        """

        errors = []

        for record in immunization_data:
            doses = [
                ("d0", record.d0), ("d1", record.d1),
                ("d2", record.d2), ("d3", record.d3)
            ]
            previous_given = True

            for dose_name, dose_value in doses:
                if not dose_value and previous_given:
                    # still fine, skip until the first missing one
                    previous_given = False
                elif dose_value and not previous_given:
                    # invalid: user tried to give dN without d(N-1)
                    # errors.append(f"{record.name.upper()}: {dose_name} cannot exist without the previous dose.")
                    name = MaternalDomainService.__check_record_naming(
                        record.name)
                    errors.append(
                        f"{name}: {dose_name} cannot exist without the previous dose.")
                    break

        return errors
