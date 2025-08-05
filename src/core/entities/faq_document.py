import pandas as pd
from io import BytesIO
from typing import List, Tuple

from src.core.contracts.document import IDocument
from src.core.enums.faq_doc_extensions import FAQDocExtensions
from src.core.enums.faq_doc_mimes import FAQDocMimeTypes
from src.core.exceptions.domain_exceptions import DomainException


class FAQDocument(IDocument):

    MAX_FILE_SIZE_MB = 5
    FILE_MAX_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
    ALLOWED_EXTENSIONS = [ext.value for ext in FAQDocExtensions]
    ALLOWED_MIMES = FAQDocMimeTypes.get_allowed_mimes()
    REQUIRED_HEADERS = ['question', 'answer']

    def process_content(self)  -> List[Tuple[str, str]]:
        self.__file_validation()
        return self.__data_extractor()

    def __data_extractor(self)  -> List[Tuple[str, str]]:
        bytes_data = BytesIO(self.file.read())
        df = pd.read_excel(bytes_data, engine='openpyxl')
        headers = df.columns.str.lower().tolist()
        missing_headers = set(self.REQUIRED_HEADERS) - set(headers)
        self.__header_validation(df, self.REQUIRED_HEADERS, headers, missing_headers)
        return self.__content_validation(df)
    
    def __content_validation(self, df: pd.DataFrame) -> List[Tuple[str, str]]:
        faq_pair = []
        for i, row in df.iterrows():
            question = str(row.get('question', '')).strip()
            answer = str(row.get('answer', '')).strip()
            self.__has_content_validation(i, question, answer)
            pair = (question, answer)
            self.__row_level_validation(i, row, question, answer)
            faq_pair.append(pair)
        return faq_pair

    def __row_level_validation(self, i, row, question, answer):
        if len(question) > 300:
            raise DomainException(f"Row {i+2} question exceeds 300 characters limit.")
                
        if len(answer) > 1000:
            raise DomainException(f"Row {i+2} answer exceeds 1000 characters limit.")

        if isinstance(question, float) or isinstance(row['answer'], float):
            raise DomainException(f"Row {i+2}: FAQ contains invalid numeric values.")

    def __has_content_validation(self, i, question, answer):
        if not question:
            raise DomainException(f"Row {i+2} is empty or has no data.")                
        if not answer:
            raise DomainException(f"Row {i+2} has no answer.")

    def __header_validation(self, df, required_headers, headers, missing_headers):
        if missing_headers:
            raise DomainException(f"Missing required headers: {missing_headers}")
            
        unexpected_headers = set(headers) - set(required_headers)
        if unexpected_headers:
            raise DomainException(f"Unexpected headers: {unexpected_headers}")
            
        if df.empty:
            raise DomainException("Uploaded file is empty.")

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
