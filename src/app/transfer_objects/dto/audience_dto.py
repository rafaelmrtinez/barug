from dataclasses import dataclass
from typing import Optional, List


@dataclass
class AudienceDTO:
    """Data Transfer Object for announcement audience operations"""
    audience_id: Optional[int] = None
    announcement_id: Optional[int] = None
    audience_scope_id: Optional[int] = None
    role_id: Optional[int] = None
    purok_sitio_id: Optional[int] = None
    audience_scope_name: Optional[str] = None
    inserted_persons: Optional[int] = None


@dataclass
class AudienceScopeDTO:
    """Data Transfer Object for audience scope"""
    audience_scope_id: int
    audience_scope_name: str


@dataclass
class AudiencePersonDTO:
    """Data Transfer Object for audience person list"""
    audience_person_list_id: Optional[int] = None
    audience_id: Optional[int] = None
    person_id: Optional[int] = None