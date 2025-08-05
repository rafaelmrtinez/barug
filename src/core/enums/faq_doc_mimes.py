from enum import Enum


class FAQDocMimeTypes(Enum):
    EXCEL_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    EXCEL_XLS = "application/vnd.ms-excel"
    
    @classmethod
    def get_allowed_mimes(cls):
        return [mime.value for mime in cls]
        