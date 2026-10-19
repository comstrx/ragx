from collections.abc import AsyncIterator, Callable
from urllib.parse import urlsplit

from core.error import Code
from core.json import json
from core.llm import Attachment, ChatGpt, Chunk, Claude, DeepSeek, Gemini, Llm, Local, Message, Options, Reply, Usage
from core.net import Answer, Ask, Transport, net
from core.test import expect, test
import os, pytest, struct, zlib

EVENTS = { "content-type": "text/event-stream" }
DELTA  = 'data: {{"type":"content_block_delta","delta":{{"type":"text_delta","text":"{text}"}}}}\n\n'

def square ( red: int, green: int, blue: int, side: int = 64 ) -> bytes:

    def chunk ( kind: bytes, data: bytes ) -> bytes:

        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    rows = b"".join(b"\x00" + bytes((red, green, blue)) * side for _ in range(side))
    head = struct.pack(">IIBBBBB", side, side, 8, 2, 0, 0, 0)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")

def payload ( body: object, status: int = 200, **headers: str ) -> Answer:

    return status, json.encode(body), { "content-type": "application/json", **headers }

def events ( *lines: str ) -> Answer:

    return 200, "".join(lines).encode(), EVENTS

def chat ( asked: Ask ) -> Answer:

    body = json.loads(asked.body)

    if body["messages"][-1]["content"] == "rate": return payload({ "error": "slow" }, 429, **{ "retry-after": "7" })
    if body.get("stream"):

        return events(
            'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n',
            'data: {"choices":[{"delta":{"content":"lo"},"finish_reason":"stop"}],'
            '"usage":{"prompt_tokens":3,"completion_tokens":2}}\n\n',
            "data: [DONE]\n\n",
        )

    return payload({
        "model": "fake-1", "choices": [{ "message": { "content": "Hello back" }, "finish_reason": "stop" }],
        "usage": { "prompt_tokens": 5, "completion_tokens": 2 },
    })

def messages ( asked: Ask ) -> Answer:

    if json.loads(asked.body).get("stream"):

        return events(
            'event: message_start\ndata: {"type":"message_start","message":{"usage":{"input_tokens":7}}}\n\n',
            DELTA.format(text="A"),
            DELTA.format(text="B"),
            'event: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":2}}\n\n',
            'event: message_stop\ndata: {"type":"message_stop"}\n\n',
        )

    return payload({
        "model": "claude-x", "content": [{ "type": "text", "text": "Hi " }, { "type": "text", "text": "there" }],
        "stop_reason": "end_turn", "usage": { "input_tokens": 7, "output_tokens": 3 },
    })

def generate ( asked: Ask ) -> Answer:

    if urlsplit(asked.url).path.endswith(":streamGenerateContent"):

        return events(
            'data: {"candidates":[{"content":{"parts":[{"text":"G1"}]}}]}\n\n',
            'data: {"candidates":[{"content":{"parts":[{"text":"G2"}]},"finishReason":"STOP"}],'
            '"usageMetadata":{"promptTokenCount":4,"candidatesTokenCount":1}}\n\n',
        )

    return payload({
        "modelVersion": "gemini-x",
        "candidates": [{ "content": { "parts": [{ "text": "Gem" }] }, "finishReason": "STOP" }],
        "usageMetadata": { "promptTokenCount": 4, "candidatesTokenCount": 1 },
    })

ROUTES: dict[str, Callable[[Ask], Answer]] = {
    "/v1/chat/completions" : chat,
    "/v1/messages"         : messages,
    "/v1/models"           : lambda _: payload({ "data": [{ "id": "b" }, { "id": "a" }] }),
    "/v1beta/models"       : lambda _: payload({ "models": [{ "name": "models/gemini-x" }] }),
}

def wire ( seen: list[Ask] ) -> Transport:

    def answer ( asked: Ask ) -> Answer:

        seen.append(asked)

        path = urlsplit(asked.url).path
        bad  = { "error": { "message": "bad key" } }

        if asked.headers.get("authorization") == "Bearer wrong": return payload(bad, 401)
        if path.startswith("/v1beta/models/"): return generate(asked)

        return ROUTES[path](asked)

    return net.mocked(answer)

def sent ( seen: list[Ask] ) -> dict[str, object]:

    found: dict[str, object] = json.loads(seen[-1].body)

    return found

async def drain ( chunks: AsyncIterator[Chunk] ) -> list[Chunk]:

    return [chunk async for chunk in chunks]

@pytest.mark.anyio
class TestLlm:

    async def test_openai_compatible_wire_sessions_files_and_streaming ( self ) -> None:

        seen: list[Ask] = []
        brain = Llm()

        brain.register(ChatGpt("secret", "fake-1", transport=wire(seen), retries=0))
        brain.register(Local("http://local/v1", "tiny", transport=wire(seen)))

        expect((brain.names(), brain.default(), brain.ready())).equals((["chatgpt", "local"], "chatgpt", True))

        reply = await brain.prompt().system("be brief").temperature(0.1).max_tokens(50).json().meta(user="u1").ask("hi")

        expect((reply.text, reply.usage.total(), reply.finish, reply.provider, reply.model)).equals(
            ("Hello back", 7, "stop", "chatgpt", "fake-1"),
        )
        expect(sent(seen)).subset({
            "model": "fake-1", "response_format": { "type": "json_object" }, "temperature": 0.1,
            "max_completion_tokens": 50, "metadata": { "user": "u1" },
            "messages.0": { "role": "system", "content": "be brief" },
        })
        expect(seen[-1].headers).subset({ "authorization": "Bearer secret", "content-type": "application/json" })

        prompt = brain.chatgpt().session()
        key    = str(prompt.session_id())

        await prompt.ask("first")
        await brain.resume(key).ask("second")

        session = brain.sessions.resume(key)

        expect([message.role for message in session.messages]).equals(["user", "assistant", "user", "assistant"])
        expect((session.turns, session.usage.total(), sent(seen)["messages"])).equals((2, 14, [
            { "role": "user", "content": "first" }, { "role": "assistant", "content": "Hello back" },
            { "role": "user", "content": "second" },
        ]))
        expect((session.trim(2), len(session.history()), session.dump()["id"])).equals((2, 2, key))

        chunks = await drain(brain.local().stream("stream it"))

        expect(("".join(chunk.text for chunk in chunks), chunks[-1].done)).equals(("Hello", True))
        expect([chunk.usage.total() for chunk in chunks if chunk.usage]).equals([5])
        expect(sent(seen)["stream"]).true()
        expect(seen[-1].headers).lacks("authorization")

        note  = Attachment.text("note.txt", "plain")
        image = Attachment("pic.png", b"\x89PNG", "image/png")

        await brain.ask("look", "local", (note, image), temperature=0.2)

        expect(sent(seen)).subset({
            "temperature": 0.2, "messages.-1.content.0": { "type": "text", "text": "look" },
            "messages.-1.content.1": { "type": "text", "text": "[note.txt]\nplain" },
        })
        expect(sent(seen)).at("messages.-1.content.2.image_url.url").starts_with("data:image/png;base64,")
        expect((await brain.models("local"), brain.estimate_tokens("abcdefgh"), brain.fits("abcd", 1))).equals(
            (["a", "b"], 2, True),
        )
        expect((brain.session("fixed", system="s").id, brain.session("fixed").system)).equals(("fixed", "s"))
        expect(await brain.sessions.forget("fixed")).true()
        expect(Reply('```json\n{"a": 1}\n```', "m", "p").json()).equals({ "a": 1 })
        expect(Usage(1, 2).plus(Usage(3, 4)).total()).equals(10)
        expect((brain.forget("local"), brain.names(), brain.describe()["default"])).equals(
            (True, ["chatgpt"], "chatgpt"),
        )

        with test.fails(Code.INTERNAL, "llm.nowhere.missing"): brain.use("nowhere")
        with test.fails(Code.NOT_FOUND, "llm.session.missing"): brain.sessions.resume("missing")

        expect(await brain.close()).equals(1)

    async def test_provider_failures_are_faults_named_by_action ( self ) -> None:

        seen: list[Ask] = []
        good  = ChatGpt("secret", "fake-1", transport=wire(seen), retries=0)
        wrong = ChatGpt("wrong", "fake-1", transport=wire(seen), retries=0)
        ask   = [Message.user("x")]

        slow   = await test.rejects(good.complete([Message.user("rate")], Options()), Code.TOO_MANY_REQUESTS,
            "llm.chatgpt.complete.rate")
        denied = await test.rejects(wrong.complete(ask, Options()), Code.UNAUTHORIZED, "llm.chatgpt.complete.key")

        expect((slow.retry_after, denied.message)).equals((7.0, "bad key"))

        await test.rejects(drain(wrong.stream(ask, Options())), Code.UNAUTHORIZED, "llm.chatgpt.stream.key")
        await test.rejects(wrong.models(), Code.UNAUTHORIZED, "llm.chatgpt.models.key")

        with test.fails(Code.INTERNAL, "llm.chatgpt.config.key"): ChatGpt("")
        with test.fails(Code.INTERNAL, "llm.claude.config.key"): Claude("")

        await good.close()
        await wrong.close()

    async def test_unsupported_capabilities_fail_before_any_request ( self ) -> None:

        seen: list[Ask] = []
        claude  = Claude("key", transport=wire(seen))
        seek    = DeepSeek("key", transport=wire(seen))
        local   = Local("http://local/v1", transport=wire(seen))
        gemini  = Gemini("key", transport=wire(seen))
        pdf     = Attachment("doc.pdf", b"%PDF", "application/pdf")
        image   = Attachment("pic.png", b"\x89", "image/png")
        archive = Attachment("a.zip", b"PK", "application/zip")

        await test.rejects(claude.complete([Message.user("x")], Options(json=True)), Code.INTERNAL,
            "llm.claude.unsupported.json")
        await test.rejects(seek.complete([Message.user("x", image)], Options()), Code.INTERNAL,
            "llm.deepseek.unsupported.images")
        await test.rejects(gemini.complete([Message.user("x")], Options(metadata={ "a": 1 })), Code.INTERNAL,
            "llm.gemini.unsupported.metadata")
        await test.rejects(gemini.complete([Message.user("x", archive)], Options()), Code.INTERNAL,
            "llm.gemini.unsupported.binary")

        with test.fails(Code.INTERNAL, "llm.local.unsupported.documents"):
            local.stream([Message.user("x", pdf)], Options())

        expect(seen).empty()

        brain = Llm()

        for provider in (claude, seek, local, gemini): brain.register(provider)

        expect((brain.which("images"), brain.which("json"))).equals(
            (["claude", "gemini", "local"], ["deepseek", "gemini", "local"]),
        )
        expect(brain.describe()["capabilities"]["deepseek"]).equals(["complete", "json", "models", "stream", "texts"])
        expect(claude.describe()).subset({
            "family": "llm", "name": "claude", "keyed": True, "base": "https://api.anthropic.com",
        })
        expect(await brain.close()).equals(4)

    async def test_claude_and_gemini_speak_their_own_wire_formats ( self ) -> None:

        seen: list[Ask] = []
        claude = Claude("key", "claude-x", transport=wire(seen))
        gemini = Gemini("gkey", "gemini-x", transport=wire(seen))
        asked  = [Message.system("sys"), Message.user("hi", Attachment("doc.pdf", b"%PDF", "application/pdf"))]
        reply  = await claude.complete(asked, Options(max_tokens=99, stop=("END",)))

        expect((reply.text, reply.usage, reply.finish)).equals(("Hi there", Usage(7, 3), "end_turn"))
        expect(sent(seen)).subset({
            "system": "sys", "max_tokens": 99, "stop_sequences": ["END"], "messages.0.content.0.type": "document",
            "messages.0.content.1": { "type": "text", "text": "hi" },
        })
        expect(seen[-1].headers).subset({ "x-api-key": "key", "anthropic-version": "2023-06-01" })

        chunks = await drain(claude.stream([Message.user("go")], Options()))

        expect(("".join(chunk.text for chunk in chunks), chunks[-1].done, chunks[-1].usage)).equals(
            ("AB", True, Usage(7, 2)),
        )
        expect(await claude.models()).equals(["a", "b"])

        reply = await gemini.complete(
            [Message.user("hi", Attachment("pic.png", b"\x89", "image/png"))],
            Options(system="sys", temperature=0.5, json=True),
        )

        expect((reply.text, reply.usage, reply.finish, reply.model)).equals(("Gem", Usage(4, 1), "STOP", "gemini-x"))
        expect(sent(seen)).subset({
            "system_instruction": { "parts": [{ "text": "sys" }] },
            "generationConfig": { "temperature": 0.5, "responseMimeType": "application/json" },
            "contents.0.role": "user", "contents.0.parts.0": { "text": "hi" },
            "contents.0.parts.1.inline_data.mime_type": "image/png",
        })
        expect((seen[-1].headers["x-goog-api-key"], urlsplit(seen[-1].url).path)).equals(
            ("gkey", "/v1beta/models/gemini-x:generateContent"),
        )

        chunks = await drain(gemini.stream([Message.user("go")], Options()))
        where  = urlsplit(seen[-1].url)

        expect(("".join(chunk.text for chunk in chunks), chunks[-1].done, chunks[-1].usage)).equals(
            ("G1G2", True, Usage(4, 1)),
        )
        expect((where.path.endswith(":streamGenerateContent"), where.query)).equals((True, "alt=sse"))
        expect((await gemini.models(), gemini.describe()["model"])).equals((["gemini-x"], "gemini-x"))

        await claude.close()
        await gemini.close()

@pytest.mark.anyio
class TestLive:

    async def test_a_configured_live_provider_answers ( self ) -> None:

        url   = os.environ.get("LLM_LIVE_URL", "")
        model = os.environ.get("LLM_LIVE_MODEL", "")

        if not url or not model: pytest.skip("set LLM_LIVE_URL and LLM_LIVE_MODEL to exercise a live provider")

        provider = Local(url, model, os.environ.get("LLM_LIVE_KEY", ""), wait=120.0)
        brain    = Llm()
        calm     = Options(temperature=0.0, max_tokens=24)

        brain.register(provider)

        try:

            reply  = await provider.complete([Message.user("Reply with the single word pong")], calm)
            chunks = [chunk async for chunk in provider.stream([Message.user("Count from one to five")], calm)]
            shaped = await provider.complete(
                [Message.user("Return a JSON object whose key ok is true")], Options(temperature=0.0, json=True),
            )
            note   = Attachment.text("note.txt", "The secret word is kiwi.")
            read   = await provider.complete([Message.user("What is the secret word in the note?", note)], calm)
            first  = await brain.ask("Remember the number 7.", session="live", temperature=0.0, max_tokens=16)
            second = await brain.ask("Which number did I ask you to remember?", session="live", max_tokens=16)

            expect((reply.text.strip() != "", reply.provider, reply.model, reply.ms > 0)).equals(
                (True, "local", model, True),
            )
            expect((reply.usage.input > 0, reply.usage.output > 0, reply.finish in ("stop", "length"))).equals(
                (True, True, True),
            )
            expect(("".join(chunk.text for chunk in chunks).strip() != "", chunks[-1].done)).equals((True, True))
            expect(json.loads(shaped.text)).instance_of(dict)
            expect(read.text.lower()).contains("kiwi")
            expect((first.text != "", second.text != "", len(brain.session("live").messages))).equals((True, True, 4))
            expect(await provider.models()).contains(model)

            await test.rejects(provider.complete([Message.user("hi")], Options(metadata={ "u": "1" })), Code.INTERNAL)
            await test.rejects(
                provider.complete([Message.user("hi", Attachment("d.pdf", b"%PDF", "application/pdf"))], calm),
                Code.INTERNAL, "llm.local.unsupported.documents",
            )

        finally: await provider.close()

    async def test_a_configured_live_vision_provider_sees_an_attached_image ( self ) -> None:

        url   = os.environ.get("LLM_LIVE_VISION_URL", "")
        model = os.environ.get("LLM_LIVE_VISION_MODEL", "")

        if not url or not model: pytest.skip("set LLM_LIVE_VISION_URL and LLM_LIVE_VISION_MODEL to see images live")

        provider = Local(url, model, wait=120.0)
        asked    = "What color fills this image? Answer with one word."
        calm     = Options(temperature=0.0, max_tokens=8)

        try:

            for color, shade in (("red", (220, 20, 20)), ("blue", (20, 40, 220))):

                picture = Attachment(f"{color}.png", square(*shade), "image/png")
                reply   = await provider.complete([Message.user(asked, picture)], calm)

                expect(reply.text.lower()).contains(color)

        finally: await provider.close()
