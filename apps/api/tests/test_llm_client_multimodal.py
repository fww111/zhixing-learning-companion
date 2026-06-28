import asyncio

import httpx

from app.llm.client import LLMClient


def test_complete_multimodal_text_sends_openai_compatible_image_payload(monkeypatch):
    client = LLMClient(
        api_key="test-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen3.7-plus",
        mock=False,
    )
    captured = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "vision answer"}}]}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):  # noqa: D401, ANN002, ANN003
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN002, ANN003
            return False

        async def post(self, url: str, headers: dict, json: dict):  # noqa: ANN201
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(
        client.complete_multimodal_text(
            "system",
            "explain image",
            [{"filename": "shot.png", "data_url": "data:image/png;base64,AAAABBBB"}],
        )
    )

    assert result == "vision answer"
    assert captured["url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert captured["json"]["model"] == "qwen3.7-plus"
    user_content = captured["json"]["messages"][1]["content"]
    assert user_content[0] == {"type": "text", "text": "explain image"}
    assert user_content[1] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAABBBB"}}
