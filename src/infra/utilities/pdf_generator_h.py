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

class PdfGeneratorH:

    def __init__(self):
        self.page_size = A5
        self.margin = 0.75 * inch

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
            fontName="Times-Bold",
            fontSize=12,
            leading=14,
            spaceBefore=10,
            spaceAfter=10,
        )

    def _build_table(self, data: List[List[Any]], available_width: float) -> Table:
        cols = len(data[0]) if data and isinstance(data[0], (list, tuple)) else 1
        col_width = available_width / max(cols, 1)
        table = Table(data, colWidths=[col_width] * cols, hAlign="LEFT")
        table.setStyle(
            TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), "Times-Roman"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        return table

    def _on_page(self, canvas, doc_obj):
        """Simple page rendering without signatures."""
        try:
            # Simple header
            canvas.setFont("Times-Bold", 12)
            canvas.setFillColor(colors.black)
            page_w = doc_obj.pagesize[0]
            canvas.drawCentredString(page_w / 2, doc_obj.pagesize[1] - 50, "BARANGAY SEÑOR SANTO NIÑO")
            
            # Page number
            canvas.setFont("Times-Roman", 9)
            page_num = canvas.getPageNumber()
            canvas.drawCentredString(page_w / 2, 30, f"Page {page_num}")
        except Exception:
            pass

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
        """Build PDF without signature fields."""
        buffer = BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=self.page_size,
            leftMargin=self.margin,
            rightMargin=self.margin,
            topMargin=self.margin + 60,
            bottomMargin=self.margin,
        )

        flow: List[Any] = []

        # Title block
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
                elems.append(Spacer(1, 12))
            else:
                elems.append(Paragraph(str(content), self.body_style))
                elems.append(Spacer(1, 10))

            try:
                hr = HRFlowable(width="100%", thickness=0.6, lineCap="round", color=colors.grey)
                if heading:
                    elems.insert(1, hr)
                else:
                    elems.insert(0, hr)
            except Exception:
                pass

            flow.extend(elems)

        # Build PDF
        try:
            doc.build(flow, onFirstPage=self._on_page, onLaterPages=self._on_page)
            pdf = buffer.getvalue()
            buffer.close()
            return pdf
        except Exception:
            try:
                buffer.close()
            except Exception:
                pass
            raise