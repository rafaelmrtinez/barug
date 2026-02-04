from dataclasses import dataclass


@dataclass
class PublishResultDTO:
    """Result of publishing an announcement"""
    announcement_id: int
    total_recipients: int