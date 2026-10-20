from collections.abc import AsyncIterator, Callable
from typing import Any
from urllib.parse import urlsplit

from core.error import Code
from core.json import json
from core.llm import (
    CORE, EMBED, HEARING, JSON, SCHEMA, TOKENS, Attachment, ChatGpt, Chunk, Claude, DeepSeek, Gemini, Llm, Local,
    Memory, Message, Model, Options, Reply, Usage,
)
from core.net import Answer, Ask, Transport, net
from core.test import expect, sample, test
import os, pytest

HEARD  : dict[str, Any] = {
    "text": "مرحبا بكم. The invoice is paid.", "language": "ar", "duration": 4.0,
    "segments": [
        { "start": 0.0, "end": 1.5, "text": " مرحبا بكم. " },
        { "start": 1.5, "end": 4.0, "text": "The invoice is paid." },
    ],
}

EVENTS = { "content-type": "text/event-stream" }
DELTA  = 'data: {{"type":"content_block_delta","delta":{{"type":"text_delta","text":"{text}"}}}}\n\n'

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

        brain.register(ChatGpt(Model("fake-1", key="secret", retries=0), wire(seen)))
        brain.register(Local(Model("tiny", "http://local/v1"), wire(seen)))

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

        prompt = brain.prompt("chatgpt").session()
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

        chunks = await drain(brain.prompt("local").stream("stream it"))

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
        good  = ChatGpt(Model("fake-1", key="secret", retries=0), wire(seen))
        wrong = ChatGpt(Model("fake-1", key="wrong", retries=0), wire(seen))
        ask   = [Message.user("x")]

        slow   = await test.rejects(good.complete([Message.user("rate")], Options()), Code.TOO_MANY_REQUESTS,
            "llm.chatgpt.complete.rate")
        denied = await test.rejects(wrong.complete(ask, Options()), Code.UNAUTHORIZED, "llm.chatgpt.complete.key")

        expect((slow.retry_after, denied.message)).equals((7.0, "bad key"))

        await test.rejects(drain(wrong.stream(ask, Options())), Code.UNAUTHORIZED, "llm.chatgpt.stream.key")
        await test.rejects(wrong.models(), Code.UNAUTHORIZED, "llm.chatgpt.models.key")

        with test.fails(Code.INTERNAL, "llm.chatgpt.config.key"): ChatGpt(Model("gpt-x"))
        with test.fails(Code.INTERNAL, "llm.claude.config.key"): Claude(Model("claude-x"))
        with test.fails(Code.INTERNAL, "llm.local.config.url"): Local(Model("tiny"))
        with test.fails(Code.INTERNAL, "llm.gemini.config.model"): Gemini(Model(key="k"))

        await good.close()
        await wrong.close()

    async def test_unsupported_capabilities_fail_before_any_request ( self ) -> None:

        seen: list[Ask] = []
        claude  = Claude(Model("claude-x", key="key"), wire(seen))
        seek    = DeepSeek(Model("deepseek-x", key="key"), wire(seen))
        local   = Local(Model("tiny", "http://local/v1"), wire(seen))
        gemini  = Gemini(Model("gemini-x", key="key"), wire(seen))
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
        claude = Claude(Model("claude-x", key="key"), wire(seen))
        gemini = Gemini(Model("gemini-x", key="gkey"), wire(seen))
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
class TestModels:

    async def test_one_spec_builds_any_driver_and_tasks_route_to_capable_models ( self ) -> None:

        writes = CORE | {JSON, SCHEMA}
        brain  = Llm()
        models = [
            Model(
                "qwen", "http://writer/v1", name="writer", driver="local", tasks=frozenset({"generate"}), serves=writes,
            ),
            Model("qwen-e", "http://vectors/v1", name="vectors", driver="local", tasks=frozenset({"embed"}),
                serves=frozenset({EMBED})),
            Model("claude-x", key="k", name="claude", driver="claude", tasks=frozenset({"generate", "summarize"})),
        ]

        brain.setup(models, "writer", tasks={ "generate": "claude" })

        expect((brain.names(), brain.default(), brain.tasks())).equals((
            ["claude", "vectors", "writer"], "writer",
            { "generate": "claude", "embed": "vectors", "summarize": "claude" },
        ))
        expect((brain.task("embed").provider().name, brain.serves("ocr"), brain.describe()["tasks"]["embed"])).equals(
            ("vectors", False, "vectors"),
        )
        expect(brain.use("claude").describe()).subset({ "keyed": True, "tasks": ["generate", "summarize"] })

        with test.fails(Code.INTERNAL, "llm.task.ocr.missing"): brain.task("ocr")
        with test.fails(Code.INTERNAL, "llm.driver.nope"): brain.build(Model("m", "http://x/v1", driver="nope"))
        with test.fails(Code.INTERNAL, "llm.vectors.task.generate"): brain.assign("generate", "vectors")
        with test.fails(Code.INTERNAL, "llm.task.fly"): Model("m", tasks=frozenset({"fly"}))
        with test.fails(Code.INTERNAL, "llm.capability.teleport"): Model("m", serves=frozenset({"teleport"}))
        with test.fails(Code.INTERNAL, "llm.model.window"): Model("m", window=16)
        with test.fails(Code.INTERNAL, "llm.blind.task.embed"):
            brain.setup([Model("m", "http://x/v1", name="blind", driver="local", tasks=frozenset({"embed"}))])

        expect((brain.forget("claude"), brain.tasks())).equals((True, { "embed": "vectors" }))
        expect(await brain.close()).equals(2)

    async def test_compaction_goes_to_the_summarizer_and_defaults_ride_the_spec ( self ) -> None:

        seen: dict[str, list[dict[str, Any]]] = { "writer": [], "notes": [] }

        def answer ( name: str, text: str ) -> Transport:

            def reply ( asked: Ask ) -> Answer:

                seen[name].append(json.loads(asked.body))

                return payload({ "choices": [{ "message": { "content": text }, "finish_reason": "stop" }] })

            return net.mocked(reply)

        calm   = Options(temperature=0.3)
        big    = Model("big", "http://w/v1", name="writer", tasks=frozenset({"generate"}), options=calm)
        small  = Model("small", "http://n/v1", name="notes", tasks=frozenset({"summarize"}))
        writer = Local(big, answer("writer", "ok"))
        notes  = Local(small, answer("notes", "NOTES"))
        brain  = Llm()

        brain.setup(memory=Memory(window=256, ratio=0.5, keep=2, chars=1.0))
        brain.register(writer)
        brain.register(notes)

        chat = brain.task("generate").session("s-1")

        for question in ("q1 " * 10, "q2 " * 10, "q3"): await chat.ask(question)

        expect([body["model"] for body in seen["notes"]]).equals(["small"])
        expect(seen["notes"][0]["messages"][0]["content"]).starts_with("Summarize the earlier conversation")
        expect((seen["writer"][0]["temperature"], brain.sessions.resume("s-1").summary)).equals((0.3, "NOTES"))

class TestTuning:

    async def test_one_vocabulary_maps_onto_each_wire_and_unknown_levels_drop ( self ) -> None:

        seen: list[Ask] = []
        tuned  = Options(effort="high", seed=7, top_k=5, presence=0.5, frequency=0.2, extra={ "service_tier": "flex" })
        gpt    = ChatGpt(Model("fake-1", key="secret"), wire(seen))
        claude = Claude(Model("claude-x", key="key"), wire(seen))
        gemini = Gemini(Model("gemini-x", key="gkey"), wire(seen))
        seek   = DeepSeek(Model("deepseek-x", key="key"), wire(seen))
        local  = Local(Model("tiny", "http://local/v1"), wire(seen))
        asked  = [Message.user("hi")]

        await gpt.complete(asked, tuned)

        expect(sent(seen)).subset({
            "reasoning_effort": "high", "seed": 7, "presence_penalty": 0.5, "frequency_penalty": 0.2,
            "service_tier": "flex",
        })
        expect(sent(seen)).lacks("top_k")

        await claude.complete(asked, Options(effort="xhigh", top_k=5, seed=7, temperature=0.1))

        expect(sent(seen)).subset({ "output_config": { "effort": "xhigh" }, "top_k": 5, "temperature": 0.1 })
        expect(sent(seen)).lacks("seed")

        await claude.complete(asked, Options(effort="minimal"))

        expect(sent(seen)).lacks("output_config")

        await gemini.complete(asked, Options(effort="low", top_k=3, seed=1, presence=0.1, max_tokens=9))

        expect(sent(seen)["generationConfig"]).equals({
            "thinkingConfig": { "thinkingLevel": "low" }, "topK": 3, "seed": 1, "presencePenalty": 0.1,
            "maxOutputTokens": 9,
        })

        await gemini.complete(asked, Options(effort="max"))

        expect(sent(seen)).lacks("generationConfig")

        await seek.complete(asked, tuned)

        expect(sent(seen)).lacks("reasoning_effort", "seed", "top_k")

        await local.complete(asked, Options(effort="none", top_k=40, max_tokens=12))

        expect(sent(seen)).subset({ "reasoning_effort": "none", "top_k": 40, "max_tokens": 12 })
        expect((gpt.describe()["tunes"], seek.describe()["efforts"])).equals((
            ["effort", "frequency", "presence", "seed", "stop", "temperature", "top_p"], [],
        ))

        brain = Llm()

        brain.register(local)

        await test.rejects(brain.ask("x", top_k=0), Code.VALIDATION, "llm.options.top_k")
        await test.rejects(brain.ask("x", presence=3.0), Code.VALIDATION, "llm.options.penalty")

        for provider in (gpt, claude, gemini, seek, local): await provider.close()

class TestTranscription:

    async def test_audio_posts_as_multipart_and_comes_back_as_timed_segments ( self ) -> None:

        seen: list[Ask] = []
        body: list[dict[str, Any]] = [HEARD]

        def answer ( asked: Ask ) -> Answer:

            seen.append(asked)

            return payload(body[0])

        listener = Local(Model("whisper", "http://hear/v1", serves=HEARING), net.mocked(answer))
        brain    = Llm()
        sound    = Attachment("clip.wav", b"RIFF0000WAVE", "audio/wav")

        brain.register(listener)

        heard = await brain.transcribe(sound, language="ar")
        form  = seen[-1].body.decode(errors="replace")

        expect((urlsplit(seen[-1].url).path, seen[-1].headers["content-type"])).satisfies(
            lambda found: found[0] == "/v1/audio/transcriptions" and found[1].startswith("multipart/form-data"),
        )
        expect(form).contains('name="model"', "whisper", "verbose_json", 'name="language"', 'filename="clip.wav"')
        expect(([(item.text, item.start, item.end) for item in heard.segments], heard.language)).equals((
            [("مرحبا بكم.", 0.0, 1.5), ("The invoice is paid.", 1.5, 4.0)], "ar",
        ))
        expect(heard.text()).equals("مرحبا بكم. The invoice is paid.")

        body[0] = { "text": "whole", "duration": 2.5 }

        expect([(item.text, item.end) for item in (await listener.transcribe(sound)).segments]).equals([("whole", 2.5)])

        for broken in ({ "text": "x", "segments": [{ "start": 2, "end": 1, "text": "y" }] }, { "segments": 3 }):

            body[0] = broken

            await test.rejects(listener.transcribe(sound), Code.UNAVAILABLE)

        written = Attachment.text("a.txt", "x")

        await test.rejects(listener.transcribe(written), Code.VALIDATION, "llm.transcribe.media")
        await test.rejects(brain.prompt().system("x").transcribe(sound), Code.VALIDATION, "llm.dedicated.options")
        deaf = Local(Model("tiny", "http://local/v1"))

        await test.rejects(deaf.transcribe(sound), Code.INTERNAL, "llm.local.unsupported.transcribe")

        expect(ChatGpt(Model("gpt-4o-transcribe", key="k")).abilities()).equals(HEARING)

        await listener.close()

@pytest.mark.anyio
class TestLive:

    async def test_a_configured_live_provider_answers ( self ) -> None:

        url   = os.environ.get("LLM_LIVE_URL", "")
        model = os.environ.get("LLM_LIVE_MODEL", "")

        if not url or not model: pytest.skip("set LLM_LIVE_URL and LLM_LIVE_MODEL to exercise a live provider")

        provider = Local(Model(model, url, os.environ.get("LLM_LIVE_KEY", ""), timeout=120.0, retries=0))
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

            served = CORE | {TOKENS}
            exact  = Local(Model(model, url, os.environ.get("LLM_LIVE_KEY", ""), timeout=120.0, serves=served))
            short = await exact.count([Message.user("Hello")], calm)
            long  = await exact.count([Message.user("Hello " * 40)], calm)

            await exact.close()

            expect((short > 0, long > short + 30)).equals((True, True))

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

        provider = Local(Model(model, url, timeout=120.0, retries=0))
        asked    = "What color fills this image? Answer with one word."
        calm     = Options(temperature=0.0, max_tokens=8)

        try:

            for color, shade in (("red", (220, 20, 20)), ("blue", (20, 40, 220))):

                picture = Attachment(f"{color}.png", sample.png(*shade), "image/png")
                reply   = await provider.complete([Message.user(asked, picture)], calm)

                expect(reply.text.lower()).contains(color)

        finally: await provider.close()
