import json

import httpx
import pytest
import respx
from pydantic import BaseModel

from app.config import Settings
from app.llm import LLMError, OllamaClient


class Out(BaseModel):
    answer: str
    score: float


def make_client() -> OllamaClient:
    return OllamaClient(Settings(ollama_url="http://ollama.test", llm_json_retries=2))


def chat_reply(content: str) -> httpx.Response:
    return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})


@respx.mock
async def test_generate_json_valid_first_try():
    route = respx.post("http://ollama.test/api/chat").mock(
        return_value=chat_reply(json.dumps({"answer": "ok", "score": 0.5}))
    )
    out = await make_client().generate_json(Out, "sys", "user")
    assert out == Out(answer="ok", score=0.5)
    sent = json.loads(route.calls[0].request.content)
    assert sent["format"]["properties"]["answer"]  # schema forwarded to Ollama
    assert sent["stream"] is False


@respx.mock
async def test_generate_json_retries_with_error_feedback():
    route = respx.post("http://ollama.test/api/chat").mock(
        side_effect=[chat_reply('{"answer": "x"}'), chat_reply('{"answer": "x", "score": 1}')]
    )
    out = await make_client().generate_json(Out, "sys", "user")
    assert out.score == 1.0
    second = json.loads(route.calls[1].request.content)["messages"]
    assert "failed validation" in second[-1]["content"]


@respx.mock
async def test_generate_json_gives_up_after_retries():
    respx.post("http://ollama.test/api/chat").mock(return_value=chat_reply("not json"))
    with pytest.raises(LLMError, match="No valid JSON"):
        await make_client().generate_json(Out, "sys", "user")


@respx.mock
async def test_connect_error_is_actionable():
    respx.post("http://ollama.test/api/chat").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(LLMError, match="Is it running"):
        await make_client().chat([{"role": "user", "content": "hi"}])


@respx.mock
async def test_health_reports_down_without_raising():
    respx.get("http://ollama.test/api/tags").mock(side_effect=httpx.ConnectError("refused"))
    result = await make_client().health()
    assert result["ok"] is False
