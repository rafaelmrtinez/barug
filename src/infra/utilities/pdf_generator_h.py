from io import BytesIO
from typing import List, Dict, Any, Optional

from reportlab.lib.pagesizes import A5
from reportlab.lib.units import inch
from datetime import datetime
from zoneinfo import ZoneInfo
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)
from reportlab.platypus.flowables import HRFlowable

from src.infra.utilities.pdf_settings import PdfSettings
from src.infra.utilities.pdf_render_helpers import PdfRenderHelpers


class PdfGeneratorH:
    """Reusable, data-driven PDF generator without signature fields.

    See src.infra.utilities.pdf_settings.PdfSettings for defaults that can be
    overridden by creating this class with a custom PdfSettings instance.
    """

    def __init__(self, settings: Optional[PdfSettings] = None):
        self.settings = settings or PdfSettings()
        self.page_size = self.settings.page_size
        self.margin = self.settings.margin_inch * inch

        # Styles
        self.sample = getSampleStyleSheet()
        self.body_style = ParagraphStyle(
            "Body",
            parent=self.sample["Normal"],
            fontName="Times-Roman",
            fontSize=11,
            leading=13,
        )
        self.heading_style = ParagraphStyle(
            "Heading",
            parent=self.sample["Heading2"],
            # Use a semi-bold font for section headings so they are
            # visually identifiable in the generated PDF.
            fontName="Times-Bold",
            fontSize=12,
            leading=14,
            # increase spacing around headings so horizontal rules and
            # tables don't collide with heading text
            spaceBefore=10,
            spaceAfter=10,
        )

        # Runtime attributes populated by generate() before build()
        self._left_image_path: Optional[str] = None
        self._right_image_path: Optional[str] = None
        self._header_height: float = 0.0
        self._watermark_text: Optional[str] = None
        self._header_lines_to_use: Optional[List[tuple]] = None

    def _build_table(self, data: List[List[Any]], available_width: float) -> Table:
        cols = len(data[0]) if data and isinstance(data[0], (list, tuple)) else 1
        col_width = available_width / max(cols, 1)
        table = Table(data, colWidths=[col_width] * cols, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Times-Roman"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return table

    def _on_page(self, canvas, doc_obj):
        """Delegate page rendering (header, watermark, footer) to helper."""
        PdfRenderHelpers.on_page(
            canvas=canvas,
            doc_obj=doc_obj,
            settings=self.settings,
            left_image_path=self._left_image_path,
            right_image_path=self._right_image_path,
            header_height=self._header_height,
            watermark_text=self._watermark_text,
            header_lines=self._header_lines_to_use,
        )

    def generate(
        self,
        title: Optional[str] = None,
        header_lines: Optional[List[tuple]] = None,
        header_color: Optional[str] = None,
        left_image_path: Optional[str] = None,
        right_image_path: Optional[str] = None,
        watermark_text: Optional[str] = None,
        sections: Optional[List[Dict[str, Any]]] = None,
        additional_signatory_name: Optional[str] = None,
        additional_signatory_role: Optional[str] = None,
    ) -> bytes:
        """Build the PDF and return bytes without signature fields.

        sections: list of dicts with keys:
          - heading: optional string
          - content: string (paragraph) or list-of-lists (table rows)
        """
        buffer = BytesIO()

        # resolve header lines and compute height reserved for header
        header_lines_to_use = header_lines or self.settings.default_header_lines
        logo_room = 0.9 * inch
        header_height = PdfRenderHelpers.compute_header_height(
            header_lines_to_use, self.settings.header_bottom_margin, logo_room
        )

        # store runtime attrs for page callback
        # allow caller to override header_color for this generation
        if header_color:
            try:
                self.settings.header_color = header_color
            except Exception:
                pass

        self._left_image_path = left_image_path
        self._right_image_path = right_image_path
        self._header_height = header_height
        self._watermark_text = watermark_text or self.settings.default_watermark
        self._header_lines_to_use = header_lines_to_use

        doc = SimpleDocTemplate(
            buffer,
            pagesize=self.page_size,
            leftMargin=self.margin,
            rightMargin=self.margin,
            topMargin=self.margin + header_height,
            bottomMargin=self.margin,
        )

        flow: List[Any] = []

        # Title block with generated timestamp
        if title:
            title_style = ParagraphStyle(
                "Title",
                parent=self.sample["Heading1"],
                fontName="Times-Bold",
                fontSize=13,
                leading=13,
                alignment=TA_CENTER,
                spaceBefore=3,
                spaceAfter=3,
            )
            flow.append(Paragraph(str(title), title_style))

            try:
                tz = ZoneInfo("Asia/Manila")
                now_manila = datetime.now(tz)
            except Exception:
                now_manila = datetime.now()

            date_str = now_manila.strftime("%B %d, %Y")
            time_str = now_manila.strftime("%I:%M %p")

            meta_style = ParagraphStyle(
                "Meta",
                parent=self.sample["Normal"],
                fontName="Times-Roman",
                fontSize=9,
                leading=10,
                alignment=TA_CENTER,
                spaceBefore=1,
                spaceAfter=1,
            )
            flow.append(Paragraph(f"Date: {date_str}", meta_style))
            flow.append(Paragraph(f"Time: {time_str}", meta_style))
            flow.append(Spacer(1, 6))

        if not sections:
            sections = []

        for sec in sections:
            elems: List[Any] = []
            heading = sec.get("heading")
            content = sec.get("content")

            if heading:
                elems.append(Paragraph(str(heading), self.heading_style))

            if content is None:
                continue

            if isinstance(content, list) and content and isinstance(content[0], (list, tuple)):
                table = self._build_table(content, available_width=doc.width)
                elems.append(table)
                # add a slightly larger spacer after tables so following
                # horizontal rules or headings don't overlap
                elems.append(Spacer(1, 12))
            else:
                elems.append(Paragraph(str(content), self.body_style))
                # paragraphs get a bit more breathing room as well
                elems.append(Spacer(1, 10))

            try:
                hr = HRFlowable(width="100%", thickness=0.6, lineCap="round", color=colors.grey)
                # insert a small rule after heading if present
                if heading:
                    elems.insert(1, hr)
                else:
                    elems.insert(0, hr)
            except Exception:
                pass

            flow.extend(elems)

        # Build PDF with instance page-callback (NO SIGNATURE FIELDS)
        try:
            doc.build(flow, onFirstPage=self._on_page, onLaterPages=self._on_page)
            pdf = buffer.getvalue()
            buffer.close()
            return pdf
        except Exception:
            # If building failed, ensure we close buffer and re-raise
            try:
                buffer.close()
            except Exception:
                pass
            raise