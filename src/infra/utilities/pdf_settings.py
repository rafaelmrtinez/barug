from dataclasses import dataclass
from typing import List, Optional, Tuple
from reportlab.lib.pagesizes import A5


@dataclass
class PdfSettings:
    """Reusable PDF settings for PdfGenerator.

    Holds defaults that can be overridden per-generate() call. This keeps
    configuration separate from rendering logic and makes the generator
    data-driven.
    """
    page_size: any = A5
    margin_inch: float = 0.5
    header_color: str = "#002060"
    # default header lines: list of (text, font_size)
    default_header_lines: Optional[List[Tuple[str, int]]] = None
    default_watermark: str = "CONFIDENTIAL HEALTH INFORMATION"
    # reserved extra spacing under header in points
    header_bottom_margin: int = 12

    def __post_init__(self):
        if self.default_header_lines is None:
            self.default_header_lines = [
                ("Republic of the Philippines", 14),
                ("Barangay Health Center", 14),
                ("BARANGAY SEÑOR SANTO NIÑO", 14),
                ("032 Legaspi Street, Cebu City", 11),
            ]
