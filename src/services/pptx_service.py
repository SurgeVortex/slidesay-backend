from io import BytesIO
from pptx import Presentation
from pptx.util import Pt, Inches
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor
from typing import Dict, Any, List

class PptxService:
    THEMES = {
        "professional": {
            "title_color": RGBColor(255, 255, 255),
            "accent_color": RGBColor(30, 60, 110),
            "background": RGBColor(30, 60, 110),
            "font": "Calibri",
        },
        "education": {
            "title_color": RGBColor(0, 96, 100),
            "accent_color": RGBColor(67, 160, 71),
            "background": RGBColor(178, 223, 219),
            "font": "Calibri",
        },
        "minimal": {
            "title_color": RGBColor(60, 60, 60),
            "accent_color": RGBColor(200, 200, 200),
            "background": RGBColor(255, 255, 255),
            "font": "Calibri",
        },
    }

    def generate(self, presentation_data: dict, theme: str = "professional", watermark: bool = False) -> bytes:
        theme_opts = self.THEMES[theme if theme in self.THEMES else "professional"]
        prs = Presentation()
        # Set default font globally (limited support in python-pptx)
        self._set_default_fonts(prs, theme_opts["font"])

        slides = presentation_data.get("slides", [])
        for idx, slide in enumerate(slides):
            slide_type = slide.get("type", "content")
            if slide_type == "title":
                self._add_title_slide(prs, slide, theme_opts)
            elif slide_type == "content":
                self._add_content_slide(prs, slide, theme_opts)
            elif slide_type == "two-column":
                self._add_two_column_slide(prs, slide, theme_opts)
            elif slide_type == "section":
                self._add_section_slide(prs, slide, theme_opts)
            else:
                self._add_content_slide(prs, slide, theme_opts)
        # Empty case: Add a title slide if no slides and title present
        if len(slides) == 0 and presentation_data.get("title"):
            self._add_title_slide(prs, {"title": presentation_data["title"]}, theme_opts)

        if watermark:
            for slide in prs.slides:
                self._add_watermark(slide)
        # Save to bytes
        bio = BytesIO()
        prs.save(bio)
        bio.seek(0)
        return bio.read()

    def _set_default_fonts(self, prs: Presentation, font_name: str):
        # In python-pptx, there is no full global font setter, but we can set font in each shape
        pass  # Font is set per-text/run in helpers

    def _add_title_slide(self, prs: Presentation, slide_data: Dict[str, Any], theme: Dict[str, Any]):
        layout = prs.slide_layouts[0]  # Title Slide
        slide = prs.slides.add_slide(layout)
        slide.shapes.title.text = slide_data.get("title", "")
        self._style_textbox(slide.shapes.title, theme, is_title=True)
        subtitle = slide.placeholders[1] if len(slide.placeholders) > 1 else None
        if subtitle:
            subtitle.text = slide_data.get("subtitle", "")
            self._style_textbox(subtitle, theme, is_title=False)
        if slide_data.get("notes"):
            self._add_notes(slide, slide_data["notes"], theme)
        background = slide.background.fill
        background.solid()
        background.fore_color.rgb = theme["background"]

    def _add_content_slide(self, prs: Presentation, slide_data: Dict[str, Any], theme: Dict[str, Any]):
        layout = prs.slide_layouts[1]  # Title and Content
        slide = prs.slides.add_slide(layout)
        slide.shapes.title.text = slide_data.get("title", "")
        self._style_textbox(slide.shapes.title, theme, is_title=True)
        bullets = slide_data.get("bullets", [])
        if bullets and len(slide.placeholders) > 1:
            content = slide.placeholders[1]
            content.text = ""
            for bullet in bullets:
                p = content.text_frame.add_paragraph()
                p.text = bullet
                p.level = 0
                p.font.size = Pt(18)
                p.font.name = theme["font"]
                p.font.color.rgb = theme["title_color"]
            # Remove leading empty paragraph if necessary
            if content.text_frame.paragraphs[0].text == "":
                content.text_frame._element.remove(content.text_frame.paragraphs[0]._p)
        if slide_data.get("notes"):
            self._add_notes(slide, slide_data["notes"], theme)
        background = slide.background.fill
        background.solid()
        background.fore_color.rgb = theme["background"]

    def _add_two_column_slide(self, prs: Presentation, slide_data: Dict[str, Any], theme: Dict[str, Any]):
        layout = prs.slide_layouts[3] if len(prs.slide_layouts) > 3 else prs.slide_layouts[1]  # Two Content or fallback
        slide = prs.slides.add_slide(layout)
        slide.shapes.title.text = slide_data.get("title", "")
        self._style_textbox(slide.shapes.title, theme, is_title=True)

        # Remove auto content placeholders if used (support non-standard layouts)
        # We'll create our own textboxes side-by-side
        if len(slide.placeholders) > 2:
            for idx in range(1, len(slide.placeholders)):
                try:
                    slide.placeholders[idx].element.getparent().remove(slide.placeholders[idx].element)
                except Exception:
                    pass
        left = slide.shapes.add_textbox(Inches(0.7), Inches(1.8), Inches(4.1), Inches(4.0))
        right = slide.shapes.add_textbox(Inches(5.1), Inches(1.8), Inches(4.1), Inches(4.0))
        self._populate_column(left, slide_data.get("left", {}), theme)
        self._populate_column(right, slide_data.get("right", {}), theme)
        if slide_data.get("notes"):
            self._add_notes(slide, slide_data["notes"], theme)
        background = slide.background.fill
        background.solid()
        background.fore_color.rgb = theme["background"]

    def _add_section_slide(self, prs: Presentation, slide_data: Dict[str, Any], theme: Dict[str, Any]):
        layout = prs.slide_layouts[2] if len(prs.slide_layouts) > 2 else prs.slide_layouts[0]
        slide = prs.slides.add_slide(layout)
        placeholder = self._get_section_header_placeholder(slide)
        if placeholder:
            placeholder.text = slide_data.get("title", "")
            self._style_textbox(placeholder, theme, is_title=True, section_header=True)
        else:
            left, top, w, h = Inches(1), Inches(2), Inches(8), Inches(3)
            tb = slide.shapes.add_textbox(left, top, w, h)
            frame = tb.text_frame
            p = frame.add_paragraph()
            p.text = slide_data.get("title", "")
            p.font.size = Pt(36)
            p.font.bold = True
            p.font.name = theme["font"]
            p.font.color.rgb = theme["title_color"]
            frame.paragraphs[0].alignment = 1  # Center
        if slide_data.get("notes"):
            self._add_notes(slide, slide_data["notes"], theme)
        background = slide.background.fill
        background.solid()
        background.fore_color.rgb = theme["background"]

    def _get_section_header_placeholder(self, slide):
        # Try matching the section header placeholder in layouts
        for shape in slide.shapes:
            if shape.is_placeholder:
                if "section" in shape.name.lower() or "header" in shape.name.lower():
                    return shape
        return slide.shapes.title if hasattr(slide.shapes, 'title') else None

    def _add_notes(self, slide, notes: str, theme: Dict[str, Any]):
        notes_slide = slide.notes_slide
        text_frame = notes_slide.notes_text_frame
        text_frame.clear()
        p = text_frame.add_paragraph()
        p.text = notes
        p.font.size = Pt(12)
        p.font.name = theme["font"]
        p.font.color.rgb = RGBColor(80, 80, 80)

    def _style_textbox(self, shape, theme, is_title=False, section_header=False):
        frame = shape.text_frame
        for i, p in enumerate(frame.paragraphs):
            if is_title or section_header:
                p.font.size = Pt(28 if not section_header else 36)
                p.font.bold = True
            else:
                p.font.size = Pt(18)
            p.font.name = theme["font"]
            p.font.color.rgb = theme["title_color"]
        frame.word_wrap = True
        try:
            frame.vertical_anchor = 1  # Center vertical
        except Exception:
            pass

    def _populate_column(self, shape, col_data, theme):
        frame = shape.text_frame
        frame.clear()
        heading = col_data.get("heading", "")
        if heading:
            p = frame.add_paragraph()
            p.text = heading
            p.font.size = Pt(21)
            p.font.bold = True
            p.font.name = theme["font"]
            p.font.color.rgb = theme["title_color"]
        for bullet in col_data.get("bullets", []):
            p = frame.add_paragraph()
            p.text = bullet
            p.level = 0
            p.font.size = Pt(18)
            p.font.name = theme["font"]
            p.font.color.rgb = theme["title_color"]
        frame.word_wrap = True

    def _add_watermark(self, slide):
        # Add "Made with SlideSay" at bottom-right in small gray text
        left = Inches(8.0)
        top = Inches(6.88)
        width = Inches(2.0)
        height = Inches(0.4)
        tb = slide.shapes.add_textbox(left, top, width, height)
        frame = tb.text_frame
        frame.clear()
        p = frame.add_paragraph()
        p.text = "Made with SlideSay"
        p.font.size = Pt(12)
        p.font.name = "Calibri"
        p.font.color.rgb = RGBColor(180, 180, 180)
        frame.word_wrap = True
        p.alignment = 2  # right
