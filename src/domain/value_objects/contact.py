from dataclasses import dataclass
from typing import Optional
import re


@dataclass(frozen=True)
class Contact:
	email: Optional[str] = None
	mobile: Optional[str] = None
	is_email_verified: bool = False

	def __post_init__(self):
		# basic email validation (not strict)
		if self.email:
			if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", self.email):
				raise ValueError(f"Invalid email address: {self.email}")
		if self.mobile:
			# normalise: allow digits, + and spaces
			if not re.match(r"^[\d +()-]{7,20}$", self.mobile):
				raise ValueError(f"Invalid mobile number: {self.mobile}")

	def masked_mobile(self) -> Optional[str]:
		if not self.mobile:
			return None
		s = self.mobile.strip()
		if len(s) <= 4:
			return '****'
		return '*' * (len(s) - 4) + s[-4:]
