import random
import datetime
import pytz


class IdentificationGenerator:
    
    @staticmethod
    def generate_suffix(length: int = 4):
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ2346789"
        return ''.join(random.choices(alphabet, k=length))
    
    @staticmethod
    def generate_family_number(household_id: str, family_count: int) -> str:
        return f"HH{household_id}-FAM00{family_count + 1}"

    @staticmethod
    def generate_household_number(house_number: int | str, month: str, year: str) -> str:
        current_time = datetime.datetime.now(pytz.timezone('Asia/Manila'))
        
        try:
            padded = f"{int(house_number):04d}"
        except ValueError:
            padded = str(house_number).zfill(4)

        return f"HH-{padded}-{year}{month}-{IdentificationGenerator.generate_suffix()}"

    @staticmethod
    def generate_ucf_number(household_id: int, total_family_count: int) -> str:
        return f"UFC-{household_id}-{total_family_count + 1}"
