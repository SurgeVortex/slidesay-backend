import pytest
from src.services.pdf_service import PdfService

BASIC_PRESENTATION = {
    "title": "Basic",
    "slides": [
        {"type": "title", "title": "T", "subtitle": "S", "notes": ""},
        {"type": "content", "title": "CT", "bullets": ["A", "B"], "notes": ""},
        {"type": "two-column", "title": "TT", "left": {"heading": "L", "bullets": ["1"]}, "right": {"heading": "R", "bullets": ["2"]}, "notes": ""}
    ]
}

@pytest.fixture
def pdf_service():
    return PdfService()

def is_valid_pdf(data: bytes) -> bool:
    return data[:4] == b'%PDF'

def test_generate_basic(pdf_service):
    data = pdf_service.generate(BASIC_PRESENTATION)
    assert is_valid_pdf(data)
    assert len(data) > 0

def test_slide_count(pdf_service):
    data = pdf_service.generate(BASIC_PRESENTATION)
    assert data and is_valid_pdf(data)

def test_title_slide(pdf_service):
    slides = [{"type": "title", "title": "Big Title", "subtitle": "Sub"}]
    pres = {"title": "T", "slides": slides}
    data = pdf_service.generate(pres)
    assert is_valid_pdf(data)

def test_content_slide(pdf_service):
    slides = [{"type": "content", "title": "S", "bullets": ["X", "Y"]}]
    pres = {"title": "T", "slides": slides}
    data = pdf_service.generate(pres)
    assert is_valid_pdf(data)

def test_two_column(pdf_service):
    slides = [{
        "type": "two-column",
        "title": "Col", "left": {"heading": "L", "bullets": ["L1"]}, "right": {"heading": "R", "bullets": ["R1"]}
    }]
    pres = {"title": "T", "slides": slides}
    data = pdf_service.generate(pres)
    assert is_valid_pdf(data)

def test_watermark(pdf_service):
    data = pdf_service.generate(BASIC_PRESENTATION, watermark=True)
    assert is_valid_pdf(data)

def test_empty_slides(pdf_service):
    pres = {"title": "Nothing", "slides": []}
    data = pdf_service.generate(pres)
    assert is_valid_pdf(data)
    assert len(data) > 0
