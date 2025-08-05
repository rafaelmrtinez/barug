import pandas as pd

from src.core.contracts.document import IDocument
from src.core.enums.faq_doc_extensions import FAQDocExtensions
from src.core.enums.faq_doc_mimes import FAQDocMimeTypes
from src.core.exceptions.domain_exceptions import DomainException


class FAQDocument(IDocument):

    MAX_FILE_SIZE_MB = 5
    FILE_MAX_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
    ALLOWED_EXTENSIONS = [ext.value for ext in FAQDocExtensions]
    ALLOWED_MIMES = FAQDocMimeTypes.get_allowed_mimes()

    def process_content(self):
        self.__file_validation()

    def __file_validation(self):
        if self.file is None:
            raise DomainException("No file content to process.")

        if self.file.size < 1:
            raise DomainException("File is empty.")

        if self.file.size > self.FILE_MAX_SIZE:
            raise DomainException(
                f"File size exceeds the maximum limit of {self.MAX_FILE_SIZE_MB} MB.")

        file_ext = self.file.name.split('.')[-1].lower()
        if file_ext not in self.ALLOWED_EXTENSIONS:
            raise DomainException(f"Unsupported file extension: {file_ext}, only {self.ALLOWED_EXTENSIONS} are allowed.")

        if self.file.content_type not in self.ALLOWED_MIMES:
            raise DomainException(
                f"Unsupported content type: {self.file.content_type}")
