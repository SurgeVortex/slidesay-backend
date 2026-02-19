import json
from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import Request, Response

from src.services.llm_service import MODELS, LLMService


class MockResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code
        self.request = Request(method='POST', url='http://test')
    def json(self):
        return self._json_data
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"Status code: {self.status_code}", request=self.request, response=Response(self.status_code, request=self.request)
            )

@pytest.mark.asyncio
async def test_structure_transcript_success(mocker):
    # Mocks httpx.AsyncClient.post to return a valid json
    slide_json = {
        "title": "My Slides",
        "slides": [
            {"type": "title", "title": "Main", "subtitle": "Sub", "notes": "Hello"},
            {"type": "content", "title": "Foo", "bullets": ["1"], "notes": "Bar"}
        ]
    }
    response_content = {
        "choices": [
            {"message": {"content": json.dumps(slide_json)}}
        ]
    }
    post_mock = AsyncMock(return_value=MockResponse(response_content, 200))
    mocker.patch("httpx.AsyncClient.post", post_mock)
    svc = LLMService(api_key="FAKE")
    transcript = "Here is my transcript"
    result = await svc.structure_transcript(transcript)
    assert result["title"] == "My Slides"
    assert result["slides"][0]["type"] == "title"
    post_mock.assert_called_once()

@pytest.mark.asyncio
async def test_structure_transcript_fallback(mocker):
    # First model fails, second succeeds
    slide_json = {
        "title": "Rescued",
        "slides": [
            {"type": "title", "title": "Main", "subtitle": "", "notes": "Hello"}
        ]
    }
    response_content = {
        "choices": [
            {"message": {"content": json.dumps(slide_json)}}
        ]
    }
    post_mock = AsyncMock(side_effect=[httpx.HTTPStatusError("fail", request=None, response=None), MockResponse(response_content, 200)])
    mocker.patch("httpx.AsyncClient.post", post_mock)
    svc = LLMService(api_key="FAKE")
    transcript = "something"
    result = await svc.structure_transcript(transcript)
    assert result["title"] == "Rescued"
    assert post_mock.call_count == 2

@pytest.mark.asyncio
async def test_structure_transcript_all_fail(mocker):
    # All models fail
    post_mock = AsyncMock(side_effect=httpx.HTTPStatusError("fail", request=None, response=None))
    mocker.patch("httpx.AsyncClient.post", post_mock)
    svc = LLMService(api_key="FAKE")
    transcript = "fail all"
    with pytest.raises(RuntimeError):
        await svc.structure_transcript(transcript)
    assert post_mock.call_count == len(MODELS)

@pytest.mark.asyncio
async def test_structure_transcript_invalid_json(mocker):
    # Model returns non-JSON content
    response_content = {
        "choices": [
            {"message": {"content": "not a json!"}}
        ]
    }
    post_mock = AsyncMock(return_value=MockResponse(response_content, 200))
    mocker.patch("httpx.AsyncClient.post", post_mock)
    svc = LLMService(api_key="FAKE")
    transcript = "bad json"
    with pytest.raises(RuntimeError) as exc:
        await svc.structure_transcript(transcript)
    # Should preserve decode error in the message for debugging
    assert "Expecting value" in str(exc.value) and "last error" in str(exc.value).lower()

@pytest.mark.asyncio
async def test_structure_transcript_missing_fields(mocker):
    # Missing "title"
    incomplete_json = {"slides": []}
    response_content = {
        "choices": [
            {"message": {"content": json.dumps(incomplete_json)}}
        ]
    }
    post_mock = AsyncMock(return_value=MockResponse(response_content, 200))
    mocker.patch("httpx.AsyncClient.post", post_mock)
    svc = LLMService(api_key="FAKE")
    transcript = "doesn't matter"
    with pytest.raises(RuntimeError) as exc:
        await svc.structure_transcript(transcript)
    # Should mention missing fields in last error
    assert "last error" in str(exc.value).lower() and "title" in str(exc.value)

@pytest.mark.asyncio
async def test_no_api_key():
    svc = LLMService(api_key=None)
    with pytest.raises(ValueError, match=r"OPENROUTER_API_KEY"):
        await svc.structure_transcript("hello?")

@pytest.mark.asyncio
async def test_custom_slide_count(mocker):
    # check num_slides appears in the message prompt
    slide_json = {
        "title": "Titled",
        "slides": [
            {"type": "title", "title": "Main", "subtitle": "Sub", "notes": "Hello"}
        ]
    }
    response_content = {
        "choices": [
            {"message": {"content": json.dumps(slide_json)}}
        ]
    }
    captured_msg = {}

    async def fake_post(self, url, headers=None, json=None):
        # The user's message prompt goes in json["messages"][1]["content"]
        captured_msg["msg"] = json["messages"][1]["content"]
        return MockResponse(response_content, 200)

    mocker.patch("httpx.AsyncClient.post", fake_post)
    svc = LLMService(api_key="FAKE")
    transcript = "say stuff"
    await svc.structure_transcript(transcript, num_slides=7)
    # Confirm prompt includes slide count
    assert "approximately 7 slides" in captured_msg["msg"]
