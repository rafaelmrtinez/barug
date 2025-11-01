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


class PdfGenerator:
    """Reusable, data-driven PDF generator.

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
            fontName="Times-Roman",
            fontSize=12,
            leading=14,
            spaceAfter=6,
            spaceBefore=8,
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
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
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
        """Build the PDF and return bytes.

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
                spaceBefore=6,
                spaceAfter=8,
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
                spaceBefore=2,
                spaceAfter=2,
            )
            flow.append(Paragraph(f"Date: {date_str}", meta_style))
            flow.append(Paragraph(f"Time: {time_str}", meta_style))
            flow.append(Spacer(1, 12))

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
                elems.append(Spacer(1, 8))
            else:
                elems.append(Paragraph(str(content), self.body_style))
                elems.append(Spacer(1, 6))

            try:
                hr = HRFlowable(width="100%", thickness=0.6, lineCap="round", color=colors.grey)
                # insert a small rule after heading if present
                if heading:
                    elems.insert(1, hr)
                else:
                    elems.insert(0, hr)
            except Exception:
                pass

            flow.append(KeepTogether(elems))

        # Signature area: preserve layout: top row (midwife, barangay HW), doctor centered below
        try:
            flow.append(Spacer(1, 36))

            sig_label_style_center = ParagraphStyle(
                "siglabel_center",
                parent=self.sample["Normal"],
                fontName="Times-Roman",
                fontSize=10,
                alignment=1,
            )

            gap_pts = 36
            left_col_w = (doc.width - gap_pts) / 2.0

            left_inner = [[Spacer(1, 28)], [Paragraph("Midwife's signature over printed name", sig_label_style_center)]]
            left_table = Table(left_inner, colWidths=[left_col_w])
            left_table.setStyle(
                TableStyle([
                    ("LINEBELOW", (0, 0), (0, 0), 1.0, colors.black),
                    ("ALIGN", (0, 0), (0, 0), "CENTER"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ])
            )

            right_inner = [[Spacer(1, 28)], [Paragraph("Barangay Health Worker's signature over printed name", sig_label_style_center)]]
            right_table = Table(right_inner, colWidths=[left_col_w])
            right_table.setStyle(
                TableStyle([
                    ("LINEBELOW", (0, 0), (0, 0), 1.0, colors.black),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ])
            )

            top_sig_table = Table([[left_table, Spacer(gap_pts, 1), right_table]], colWidths=[left_col_w, gap_pts, left_col_w])
            top_sig_table.setStyle(
                TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                    ("GRID", (0, 0), (-1, -1), 0, colors.white),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ])
            )

            flow.append(Spacer(1, 12))
            flow.append(top_sig_table)

            # Doctor signature below centered
            try:
                doctor_inner = [[Spacer(1, 18)], [Paragraph("Doctor's signature over printed name", sig_label_style_center)]]
                doctor_col_w = max(doc.width * 0.4, 120)
                doctor_table = Table(doctor_inner, colWidths=[doctor_col_w], hAlign="CENTER")
                doctor_table.setStyle(
                    TableStyle([
                        ("LINEBELOW", (0, 0), (0, 0), 1.0, colors.black),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ])
                )
                flow.append(Spacer(1, 12))
                flow.append(doctor_table)
            except Exception:
                pass
        except Exception:
            pass
        # Build PDF with instance page-callback
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
