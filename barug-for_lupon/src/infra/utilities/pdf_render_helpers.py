import os
from typing import List, Tuple, Optional
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader


class PdfRenderHelpers:
    """Static helper methods for PDF rendering (header, watermark, footer).

    These are pure helpers with no side-effects outside drawing on the
    provided canvas. Keeping them static avoids inner functions and makes
    them easy to test.
    """

    @staticmethod
    def compute_header_height(header_lines: Optional[List[Tuple[str, int]]], header_bottom_margin: int, logo_room_pts: float) -> int:
        try:
            if not header_lines:
                return int(logo_room_pts) + header_bottom_margin
            sizes = [int(size) for (_t, size) in header_lines]
            text_height = sum(sizes) + (len(sizes) - 1) * 2
            return int(max(text_height, logo_room_pts)) + 12 + int(header_bottom_margin)
        except Exception:
            return int(logo_room_pts) + int(header_bottom_margin)

    @staticmethod
    def _draw_image_safe(canvas, image_path: str, x: float, y: float, max_dim: float):
        try:
            if not image_path or not os.path.exists(image_path):
                return 0, 0
            ir = ImageReader(image_path)
            iw, ih = ir.getSize()
            if iw <= 0 or ih <= 0:
                return max_dim, max_dim
            scale = min(max_dim / float(ih), max_dim / float(iw), 1.0)
            draw_w = iw * scale
            draw_h = ih * scale
            canvas.drawImage(image_path, x, y, width=draw_w, height=draw_h, preserveAspectRatio=True, mask='auto')
            return draw_w, draw_h
        except Exception:
            return 0, 0

    @staticmethod
    def on_page(canvas, doc_obj, settings, left_image_path: Optional[str], right_image_path: Optional[str], header_height: int, watermark_text: Optional[str], header_lines: Optional[List[Tuple[str, int]]] = None):
        """Draw header images, stacked header_lines (from settings), watermark and footer.

        This method matches the callable signature expected by reportlab: (canvas, doc).
        """
        try:
            page_w = doc_obj.pagesize[0]
            page_h = doc_obj.pagesize[1]
            header_top = page_h - (settings.margin_inch * 72)  # margin in points (72pt/in)
            header_bottom = header_top - header_height

            left_draw_w = right_draw_w = 0
            img_padding = 12
            max_dim = 0.9 * 72  # 0.9 inch in points

            if left_image_path and os.path.exists(left_image_path):
                x = doc_obj.leftMargin
                y = header_bottom + (header_height - max_dim) / 2.0
                lw, lh = PdfRenderHelpers._draw_image_safe(canvas, left_image_path, x, y, max_dim)
                left_draw_w = lw

            if right_image_path and os.path.exists(right_image_path):
                rw = 0
                # place at right margin
                try:
                    ir = ImageReader(right_image_path)
                    iw, ih = ir.getSize()
                    if iw > 0 and ih > 0:
                        scale = min(max_dim / float(ih), max_dim / float(iw), 1.0)
                        rw = iw * scale
                except Exception:
                    rw = 0
                x = page_w - doc_obj.rightMargin - rw
                y = header_bottom + (header_height - max_dim) / 2.0
                rw_draw, rh_draw = PdfRenderHelpers._draw_image_safe(canvas, right_image_path, x, y, max_dim)
                right_draw_w = rw_draw

            # draw stacked header lines centered between logos
            try:
                left_bound = doc_obj.leftMargin + left_draw_w + img_padding
                right_bound = page_w - doc_obj.rightMargin - right_draw_w - img_padding
                center_x = page_w / 2.0 if right_bound <= left_bound else (left_bound + right_bound) / 2.0

                lines = header_lines or settings.default_header_lines
                if lines:
                    line_gap = 4
                    total_text_height = sum([int(s) for (_t, s) in lines]) + (len(lines) - 1) * line_gap
                    text_block_top = header_top - ((header_height - total_text_height) / 2.0)
                    current_y = text_block_top
                    for (text, size) in lines:
                        try:
                            font_size = int(size)
                            baseline = current_y - font_size + 2
                            canvas.setFont("Times-Bold", font_size)
                            canvas.setFillColor(colors.HexColor(settings.header_color) if settings.header_color else colors.black)
                            canvas.drawCentredString(center_x, baseline, str(text))
                        except Exception:
                            pass
                        current_y = current_y - font_size - line_gap
            except Exception:
                pass

            # horizontal rule under header
            try:
                y_rule = header_bottom + 6
                canvas.setStrokeColor(colors.grey)
                canvas.setLineWidth(0.6)
                canvas.line(doc_obj.leftMargin, y_rule, page_w - doc_obj.rightMargin, y_rule)
            except Exception:
                pass

            # watermark
            if watermark_text:
                try:
                    canvas.saveState()
                    canvas.setFont("Times-Roman", 24)
                    canvas.setFillColorRGB(0.92, 0.92, 0.92)
                    canvas.translate(doc_obj.pagesize[0] / 2, doc_obj.pagesize[1] / 2)
                    canvas.rotate(45)
                    canvas.drawCentredString(0, 0, watermark_text)
                    canvas.restoreState()
                except Exception:
                    pass

            # footer page number
            try:
                canvas.setFont("Times-Roman", 9)
                canvas.setFillColor(colors.black)
                page_num = canvas.getPageNumber()
                footer_y = doc_obj.bottomMargin / 2
                canvas.drawCentredString(page_w / 2.0, footer_y, f"Page {page_num}")
            except Exception:
                pass
        except Exception:
            pass
