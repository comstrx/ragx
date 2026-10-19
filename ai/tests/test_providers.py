from collections.abc import Callable
from typing import Any
from core.error import Fault
from core.fs import Part
from core.json import Shape, json
from core.llm import Attachment, ChatGpt, Claude, DeepSeek, Gemini, Harness, Llm, Transcriber
import pytest

@pytest.mark.parametrize("kind", ["chatgpt", "claude", "gemini", "deepseek"])
@pytest.mark.anyio
async def test_remote_http_payload_mapping_and_output_validation (
    kind: str, serve: Callable[..., str],
) -> None:

    seen: list[tuple[str, dict[str, Any]]] = []
    def answer ( method: str, path: str, body: dict[str, Any] ) -> tuple[int, bytes, dict[str, str]]:

        seen.append((path, body))
        if kind == "claude":
            payload = {"content": [{"type": "text", "text": '{"ok":true}'}], "stop_reason": "end_turn"}
        elif kind == "gemini":
            payload = {"candidates": [{"content": {"parts": [{"text": '{"ok":true}'}]}, "finishReason": "STOP"}]}
        else: payload = {"choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}]}
        return 200, json.encode(payload), {}

    adapters: dict[str, type[ChatGpt | Claude | Gemini | DeepSeek]] = {
        "chatgpt": ChatGpt, "claude": Claude, "gemini": Gemini, "deepseek": DeepSeek,
    }
    provider = adapters[kind]("fixture-key", base=serve(answer), model="explicit-model")
    engine = Llm()
    engine.register(provider)
    shape = Shape({"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"],
                   "additionalProperties": False})
    try:
        prompt = engine.use().system("Preserve the rule.").max_tokens(64).harness(Harness(redact=True))
        result = await prompt.schema(shape, native=provider.capabilities.schema).ask("alice@example.com")
        assert result.json() == {"ok": True}
        path, payload = seen[0]
        assert "alice@example.com" not in json.dumps(payload)
        assert "Preserve the rule." in json.dumps(payload)
        if kind == "chatgpt":
            assert path.endswith("/chat/completions")
            assert payload["max_completion_tokens"] == 64
            assert "max_tokens" not in payload
            assert payload["response_format"]["type"] == "json_schema"
        elif kind == "gemini":
            assert path.endswith("/explicit-model:generateContent")
            assert payload["generationConfig"]["responseJsonSchema"] == shape.dump()
        elif kind == "claude":
            assert path == "/v1/messages"
            assert payload["max_tokens"] == 64
            assert "output_config" not in payload
            with pytest.raises(Fault): await prompt.schema(shape).ask("native schema is unavailable here")
        else:
            assert payload["model"] == "explicit-model"
            assert "Respond with JSON satisfying this schema" in payload["messages"][0]["content"]
    finally: await engine.close()

@pytest.mark.parametrize("mime", ["image/png", "audio/wav", "video/mp4"])
@pytest.mark.anyio
async def test_media_transcriber_preserves_harness_and_uses_declared_modality (
    mime: str, serve: Callable[..., str],
) -> None:

    def answer ( method: str, path: str, body: dict[str, Any] ) -> tuple[int, bytes, dict[str, str]]:

        assert "Never invent." in json.dumps(body["system_instruction"])
        assert body["contents"][0]["parts"][1]["inline_data"]["mime_type"] == mime
        data = {"parts": [{"text": "fixture transcription", "second": 1.5}]}
        return 200, json.encode({"candidates": [{
            "content": {"parts": [{"text": json.dumps(data)}]}, "finishReason": "STOP",
        }]}), {}
    engine = Llm()
    engine.register(Gemini("fixture-key", base=serve(answer)))
    try:
        transcribe = Transcriber(engine.use().system("Never invent."))
        assert await transcribe(b"fixture bytes", mime, "sample") == (Part("fixture transcription", second=1.5),)
        with pytest.raises(Fault):
            await engine.use().harness(Harness(redact=True)).attach(Attachment("sample", b"x", mime)).ask("read")
    finally: await engine.close()
