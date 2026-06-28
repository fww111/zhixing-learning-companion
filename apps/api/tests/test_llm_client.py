import asyncio

import httpx

from app.llm.client import LLMClient


def test_mock_llm_returns_stable_profile_json():
    client = LLMClient(api_key="", mock=True)

    result = asyncio.run(
        client.complete_json(
            "画像抽取",
            "学生是计算机大二，想学习机器学习，Python一般，梯度下降薄弱，喜欢动画和代码。",
        )
    )

    assert result["major"] == "计算机科学与技术"
    assert "梯度下降" in result["weak_points"]


def test_parse_json_extracts_json_from_markdown_fence():
    client = LLMClient(api_key="", mock=True)

    result = client.parse_json('```json\n{"ok": true, "value": 3}\n```')

    assert result == {"ok": True, "value": 3}


def test_parse_json_extracts_first_json_object_from_wrapped_text():
    client = LLMClient(api_key="", mock=True)

    result = client.parse_json('先说明一下输出结构。\n{"ok": true, "value": 3}\n以上是最终结果。')

    assert result == {"ok": True, "value": 3}


def test_complete_json_retries_when_first_response_is_not_json(monkeypatch):
    client = LLMClient(api_key="test-key", mock=False)
    responses = iter(
        [
            "这里先给出分析过程，但没有返回 JSON。",
            '{"profile": {"major": "计算机科学与技术", "grade": "大二"}}',
        ]
    )
    prompts: list[tuple[str, str]] = []

    async def fake_complete(system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> str:  # noqa: ARG001
        prompts.append((system_prompt, user_prompt))
        return next(responses)

    monkeypatch.setattr(client, "_complete", fake_complete)

    result = asyncio.run(client.complete_json("画像抽取", "请返回学生画像"))

    assert result == {"profile": {"major": "计算机科学与技术", "grade": "大二"}}
    assert len(prompts) == 2
    assert "只返回一个 JSON 对象" in prompts[0][0]
    assert "请把下面这段内容整理为一个合法 JSON 对象" in prompts[1][1]


def test_complete_text_retries_transient_request_error(monkeypatch):
    client = LLMClient(api_key="test-key", mock=False)
    request = httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions")
    attempts = {"count": 0}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "稳定响应"}}]}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):  # noqa: D401, ANN002, ANN003
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN002, ANN003
            return False

        async def post(self, url: str, headers: dict, json: dict):  # noqa: ANN201
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise httpx.ReadTimeout("timed out", request=request)
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(client.complete_text("系统提示", "用户提示"))

    assert result == "稳定响应"
    assert attempts["count"] == 2
