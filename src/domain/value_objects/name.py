from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Name:
	first: str
	last: str
	middle: Optional[str] = None
	suffix: Optional[str] = None

	def full(self) -> str:
		parts = [self.first]
		if self.middle:
			parts.append(self.middle)
		parts.append(self.last)
		if self.suffix:
			parts.append(self.suffix)
		return ' '.join([p for p in parts if p])

	def initials(self) -> str:
		parts = [self.first, self.middle or '', self.last]
		return ''.join([p[0].upper() for p in parts if p])
