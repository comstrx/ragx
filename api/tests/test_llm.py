from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, Request
from httpx import ASGITransport
from starlette.responses import JSONResponse, Response, StreamingResponse
from core.error import Code, Fault
from core.llm import Attachment, ChatGpt, Claude, Gemini, Llm, Local, Message, Options, Reply, Usage
import os, pytest

fake    = FastAPI()
calls   : list[dict[str, Any]] = []
headers : list[dict[str, str]] = []
paths   : list[str] = []
queries : list[str] = []
DELTA   = (
    'event: content_block_delta\n'
    'data: {{"type":"content_block_delta","delta":{{"type":"text_delta","text":"{text}"}}}}\n\n'
)

def sse ( *events: str ) -> StreamingResponse:

    async def body () -> AsyncIterator[bytes]:
        for event in events: yield event.encode()

    return StreamingResponse(body(), media_type="text/event-stream")

async def note ( request: Request ) -> dict[str, Any]:

    body: dict[str, Any] = await request.json()

    calls.append(body)
    headers.append(dict(request.headers))
    paths.append(request.url.path)
    queries.append(request.url.query)

    return body

@fake.post("/v1/chat/completions")
async def chat ( request: Request ) -> Response:

    body = await note(request)

    if request.headers.get("host") == "api.openai.com" and request.headers.get("authorization") != "Bearer secret":
        return JSONResponse({ "error": "key" }, status_code=401)
    if body["messages"][-1]["content"] == "rate": return JSONResponse({ "error": "slow" }, status_code=429)
    if body.get("stream"):

        return sse(
            'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n',
            'data: {"choices":[{"delta":{"content":"lo"},"finish_reason":"stop"}],'
            '"usage":{"prompt_tokens":3,"completion_tokens":2}}\n\n',
            "data: [DONE]\n\n",
        )

    return JSONResponse({
        "model": "fake-1", "choices": [{ "message": { "content": "Hello back" }, "finish_reason": "stop" }],
        "usage": { "prompt_tokens": 5, "completion_tokens": 2 },
    })

@fake.get("/v1/models")
async def listing () -> Response:
    return JSONResponse({ "data": [{ "id": "b" }, { "id": "a" }] })

@fake.post("/v1/messages")
async def messages ( request: Request ) -> Response:

    body = await note(request)

    if body.get("stream"):

        return sse(
            'event: message_start\ndata: {"type":"message_start","message":{"usage":{"input_tokens":7}}}\n\n',
            DELTA.format(text="A"),
            DELTA.format(text="B"),
            'event: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":2}}\n\n',
            'event: message_stop\ndata: {"type":"message_stop"}\n\n',
        )

    return JSONResponse({
        "model": "claude-x", "content": [{ "type": "text", "text": "Hi " }, { "type": "text", "text": "there" }],
        "stop_reason": "end_turn", "usage": { "input_tokens": 7, "output_tokens": 3 },
    })

@fake.post("/v1beta/models/{target}")
async def generate ( target: str, request: Request ) -> Response:

    await note(request)

    if target.endswith(":streamGenerateContent"):

        return sse(
            'data: {"candidates":[{"content":{"parts":[{"text":"G1"}]}}]}\n\n',
            'data: {"candidates":[{"content":{"parts":[{"text":"G2"}]},"finishReason":"STOP"}],'
            '"usageMetadata":{"promptTokenCount":4,"candidatesTokenCount":1}}\n\n',
        )

    return JSONResponse({
        "modelVersion": "gemini-x",
        "candidates": [{ "content": { "parts": [{ "text": "Gem" }] }, "finishReason": "STOP" }],
        "usageMetadata": { "promptTokenCount": 4, "candidatesTokenCount": 1 },
    })

@fake.get("/v1beta/models")
async def gemini_models () -> Response:
    return JSONResponse({ "models": [{ "name": "models/gemini-x" }] })

def wire () -> ASGITransport:
    return ASGITransport(app=fake)

@pytest.mark.anyio
class TestLlm:

    async def test_openai_compatible_wire_sessions_files_and_streaming ( self ) -> None:

        brain = Llm()

        brain.register(ChatGpt("secret", "fake-1", transport=wire()))
        brain.register(Local("http://local/v1", "tiny", transport=wire()))

        assert brain.names() == ["chatgpt", "local"] and brain.default() == "chatgpt" and brain.ready()

        reply = await brain.use().system("be brief").temperature(0.1).max_tokens(50).json().ask("hi")
        sent  = calls[-1]

        assert reply.text == "Hello back" and reply.usage.total() == 7 and reply.finish == "stop"
        assert reply.provider == "chatgpt" and reply.model == "fake-1" and reply.ms >= 0
        assert reply.dump()["usage"]["input"] == 5
        assert sent["model"] == "fake-1" and sent["messages"][0] == { "role": "system", "content": "be brief" }
        assert sent["response_format"] == { "type": "json_object" } and sent["temperature"] == 0.1
        assert sent["max_tokens"] == 50
        assert headers[-1]["authorization"] == "Bearer secret" and headers[-1]["content-type"] == "application/json"

        prompt = brain.chatgpt().session()
        key    = prompt.session_id()

        assert key is not None and prompt.describe()["session"] == key

        await prompt.ask("first")
        await brain.resume(key).ask("second")

        session = brain.sessions.resume(key)

        assert [message.role for message in session.messages] == ["user", "assistant", "user", "assistant"]
        assert session.turns == 2 and session.usage.total() == 14 and session.last() is not None
        assert calls[-1]["messages"] == [
            { "role": "user", "content": "first" }, { "role": "assistant", "content": "Hello back" },
            { "role": "user", "content": "second" },
        ]
        assert session.trim(2) == 2 and len(session.history()) == 2 and session.dump()["id"] == key

        chunks = [chunk async for chunk in brain.use("local").stream("stream it")]

        assert "".join(chunk.text for chunk in chunks) == "Hello" and chunks[-1].done
        assert any(chunk.usage is not None and chunk.usage.total() == 5 for chunk in chunks)
        assert calls[-1]["stream"] is True and "authorization" not in headers[-1]

        note_file = Attachment.text("note.txt", "plain")
        image     = Attachment("pic.png", b"\x89PNG", "image/png")

        await brain.use("local").attach(note_file, image).ask("look")

        content = calls[-1]["messages"][-1]["content"]

        assert content[0] == { "type": "text", "text": "look" }
        assert content[1] == { "type": "text", "text": "[note.txt]\nplain" }
        assert content[2]["image_url"]["url"].startswith("data:image/png;base64,") and image.is_image()
        assert not image.is_text()
        assert await brain.models("local") == ["a", "b"] and brain.estimate_tokens("abcdefgh") == 2
        assert brain.fits("abcd", 1)

        naked = ChatGpt("", "fake-1", transport=wire())

        with pytest.raises(Fault) as denied: await naked.complete([Message.user("x")], Options())
        with pytest.raises(Fault) as throttled: await brain.use().ask("rate")

        assert denied.value.code == Code.UNAUTHORIZED and denied.value.reason == "llm.chatgpt.key"
        assert throttled.value.code == Code.TOO_MANY_REQUESTS and throttled.value.reason == "llm.chatgpt.rate"
        assert brain.session("fixed", system="s").id == "fixed" and brain.session("fixed").system == "s"
        assert brain.sessions.has("fixed") and brain.sessions.forget("fixed") and brain.sessions.count() >= 1
        assert Reply('```json\n{"a": 1}\n```', "m", "p").json() == { "a": 1 }
        assert Usage(1, 2).plus(Usage(3, 4)).total() == 10
        assert brain.forget("local") and brain.names() == ["chatgpt"] and brain.describe()["default"] == "chatgpt"

        with pytest.raises(Fault): brain.provider("nowhere")
        with pytest.raises(Fault): brain.sessions.resume("missing")

        await brain.close()
        await naked.close()

    async def test_claude_and_gemini_speak_their_own_wire_formats ( self ) -> None:

        claude = Claude("key", "claude-x", transport=wire())
        gemini = Gemini("gkey", "gemini-x", transport=wire())
        asked  = [Message.system("sys"), Message.user("hi", Attachment("doc.pdf", b"%PDF", "application/pdf"))]
        reply  = await claude.complete(asked, Options(max_tokens=99, stop=("END",)))
        body   = calls[-1]

        assert reply.text == "Hi there" and reply.usage == Usage(7, 3) and reply.finish == "end_turn"
        assert body["system"] == "sys" and body["max_tokens"] == 99 and body["stop_sequences"] == ["END"]
        assert body["messages"][0]["content"][0]["type"] == "document"
        assert body["messages"][0]["content"][1] == { "type": "text", "text": "hi" }
        assert headers[-1]["x-api-key"] == "key" and headers[-1]["anthropic-version"] == "2023-06-01"

        chunks = [chunk async for chunk in claude.stream([Message.user("go")], Options())]

        assert "".join(chunk.text for chunk in chunks) == "AB" and chunks[-1].done and chunks[-1].usage == Usage(7, 2)
        assert await claude.models() == ["a", "b"]

        reply = await gemini.complete(
            [Message.user("hi", Attachment("pic.png", b"\x89", "image/png"))],
            Options(system="sys", temperature=0.5, json=True),
        )
        body  = calls[-1]

        assert reply.text == "Gem" and reply.usage == Usage(4, 1) and reply.finish == "STOP"
        assert reply.model == "gemini-x"
        assert body["system_instruction"] == { "parts": [{ "text": "sys" }] }
        assert body["generationConfig"] == { "temperature": 0.5, "responseMimeType": "application/json" }
        assert body["contents"][0]["role"] == "user" and body["contents"][0]["parts"][0] == { "text": "hi" }
        assert body["contents"][0]["parts"][1]["inline_data"]["mime_type"] == "image/png"
        assert headers[-1]["x-goog-api-key"] == "gkey" and paths[-1] == "/v1beta/models/gemini-x:generateContent"

        chunks = [chunk async for chunk in gemini.stream([Message.user("go")], Options())]

        assert "".join(chunk.text for chunk in chunks) == "G1G2" and chunks[-1].done and chunks[-1].usage == Usage(4, 1)
        assert paths[-1].endswith(":streamGenerateContent") and queries[-1] == "alt=sse"
        assert await gemini.models() == ["gemini-x"] and claude.describe()["keyed"]
        assert gemini.describe()["model"] == "gemini-x"

        await claude.close()
        await gemini.close()

@pytest.mark.anyio
class TestLive:

    async def test_a_configured_live_provider_answers ( self ) -> None:

        url   = os.environ.get("LLM_LIVE_URL", "")
        model = os.environ.get("LLM_LIVE_MODEL", "")

        if not url or not model: pytest.skip("set LLM_LIVE_URL and LLM_LIVE_MODEL to exercise a live provider")

        provider = Local(url, model, os.environ.get("LLM_LIVE_KEY", ""), wait=120.0)

        try:

            reply = await provider.complete([Message.user("Reply with the single word pong")], Options(max_tokens=8))

            assert reply.text.strip() and reply.provider == "local" and reply.ms > 0

        finally: await provider.close()
