from io import BytesIO
from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

class PdfService:
    def generate(self, presentation_data: dict, watermark: bool = False) -> bytes:
        """Generate PDF bytes from presentation data."""
        buf = BytesIO()
        page_width, page_height = landscape(letter)
        c = canvas.Canvas(buf, pagesize=(page_width, page_height))

        slides = presentation_data.get("slides", [])
        title = presentation_data.get("title", "")

        for idx, slide in enumerate(slides):
            slide_type = slide.get("type")
            c.setFont("Helvetica", 30)
            if slide_type == "title":
                # Large centered title and subtitle
                slide_title = slide.get("title", "")
                subtitle = slide.get("subtitle", "")
                c.setFont("Helvetica-Bold", 48)
                c.drawCentredString(page_width/2, page_height/2 + 0.5*inch, slide_title)
                c.setFont("Helvetica", 28)
                c.drawCentredString(page_width/2, page_height/2 - 0.7*inch, subtitle)
            elif slide_type == "content":
                # Title at top, bullet points
                slide_title = slide.get("title", "")
                c.setFont("Helvetica-Bold", 32)
                c.drawString(1*inch, page_height - 1.4*inch, slide_title)
                bullets = slide.get("bullets", [])
                c.setFont("Helvetica", 24)
                start_y = page_height - 2.2*inch
                for bullet in bullets:
                    c.drawString(1.3*inch, start_y, f"\u2022 {bullet}")
                    start_y -= 0.65*inch
            elif slide_type == "two-column":
                # Title, then two columns
                slide_title = slide.get("title", "")
                c.setFont("Helvetica-Bold", 32)
                c.drawString(1*inch, page_height - 1.4*inch, slide_title)
                left = slide.get("left", {})
                right = slide.get("right", {})
                c.setFont("Helvetica-Bold", 24)
                c.drawString(1*inch, page_height - 2.2*inch, left.get("heading", ""))
                c.drawString(page_width/2 + 0.2*inch, page_height - 2.2*inch, right.get("heading", ""))
                c.setFont("Helvetica", 20)
                left_bullets = left.get("bullets", [])
                right_bullets = right.get("bullets", [])
                ly = page_height - 2.8*inch
                ry = page_height - 2.8*inch
                for bullet in left_bullets:
                    c.drawString(1.15*inch, ly, f"\u2022 {bullet}")
                    ly -= 0.48*inch
                for bullet in right_bullets:
                    c.drawString(page_width/2 + 0.4*inch, ry, f"\u2022 {bullet}")
                    ry -= 0.48*inch
            elif slide_type == "section":
                # Large centered section title
                section_title = slide.get("title", "")
                c.setFont("Helvetica-Bold", 46)
                c.drawCentredString(page_width/2, page_height/2, section_title)
            else:
                # Unknown type, just show slide number
                c.setFont("Helvetica", 24)
                c.drawCentredString(page_width/2, page_height/2, f"Slide {idx+1}")

            # Optionally, add a watermark to each page
            if watermark:
                c.setFont("Helvetica-Oblique", 12)
                text = "Made with SlideSay"
                text_width = c.stringWidth(text, "Helvetica-Oblique", 12)
                margin = 0.6*inch
                c.drawString(page_width - text_width - margin, margin * 0.7, text)

            c.showPage()

        # If no slides, just create an empty cover/title page with optional watermark
        if not slides:
            c.setFont("Helvetica-Bold", 38)
            c.drawCentredString(page_width/2, page_height/2, title or "Presentation")
            if watermark:
                c.setFont("Helvetica-Oblique", 12)
                text = "Made with SlideSay"
                text_width = c.stringWidth(text, "Helvetica-Oblique", 12)
                margin = 0.6*inch
                c.drawString(page_width - text_width - margin, margin * 0.7, text)
            c.showPage()

        c.save()
        buf.seek(0)
        return buf.read()
