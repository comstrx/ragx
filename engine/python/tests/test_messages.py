from collections.abc import Callable
from urllib.parse import parse_qs, urlsplit

from engine.error import Code
from engine.json import json
from engine.mail import LogMailer, Mail, Mailgun, Message
from engine.net import Answer, Ask, net
from engine.sms import LogTexter, Sms, Telegram, Twilio, WhatsApp, phone
from engine.test import expect, test
import pytest

def recorder ( seen: list[Ask], payload: object, status: int = 200 ) -> Callable[[Ask], Answer]:

    def answer ( asked: Ask ) -> Answer:

        seen.append(asked)

        return status, json.encode(payload), { "content-type": "application/json" }

    return answer

@pytest.mark.anyio
class TestMail:

    async def test_mail_speaks_the_shared_dsl_and_refuses_what_it_cannot_send ( self ) -> None:

        own    = Mail()
        outbox = LogMailer()

        with test.fails(Code.INTERNAL, "mail.sender"): own.setup("")

        own.setup("no-reply@x.test", "Unit", outbox)

        draft   = own.to("a@x.test", " ").about("Hi").html("<p>Hi</p>").text("Hi").cc("c@x.test").bcc("b@x.test")
        letter  = draft.reply_to("r@x.test").attach("note.txt", b"note", "text/plain").tag("welcome").meta(user="u1")
        receipt = await letter.send()

        expect((receipt.provider, receipt.status, receipt.to, own.sender())).equals(
            ("log", "logged", ("a@x.test", "c@x.test", "b@x.test"), "Unit <no-reply@x.test>"),
        )
        expect((outbox.last(), outbox.count(), letter.features())).equals(
            (letter, 1, ["html", "attachments", "cc", "bcc", "tags", "metadata", "reply"]),
        )
        expect(letter.prepare()).subset({ "from": "Unit <no-reply@x.test>", "subject": "Hi", "cc": ["c@x.test"] })
        expect(outbox.count()).equals(1)

        with test.fails(Code.BAD_REQUEST, "mail.to"): await own.draft("x").text("y").send()
        with test.fails(Code.BAD_REQUEST, "mail.body"): await own.to("a@x.test").send()
        with test.fails(Code.INTERNAL, "message.unbound"): await Message.compose("x").to("a@x.test").text("y").send()
        with test.fails(Code.INTERNAL, "mail.ghost.missing"): await letter.via("ghost").send()

    async def test_mailgun_posts_multipart_forms_per_region ( self ) -> None:

        seen: list[Ask] = []
        own  = Mail()
        sink = net.mocked(recorder(seen, { "id": "<20261019.1@mg.x.test>" }))
        gun  = Mailgun("key-1", "mg.x.test", "eu", transport=sink)

        own.setup("hello@x.test", mailer=gun)

        receipt = await own.to("a@x.test").about("Hi").text("Body").html("<b>Body</b>").tag("t1").meta(user="u").attach(
            "a.txt", b"abc", "text/plain",
        ).reply_to("r@x.test").send()
        asked   = seen[0]

        expect((receipt.id, receipt.status, asked.url)).equals(
            ("20261019.1@mg.x.test", "queued", "https://api.eu.mailgun.net/v3/mg.x.test/messages"),
        )
        expect(asked.headers["authorization"]).equals("Basic YXBpOmtleS0x")
        expect(asked.headers["content-type"]).starts_with("multipart/form-data")
        expect(asked.body).contains(b'name="o:tag"', b'name="v:user"', b'name="h:Reply-To"', b'filename="a.txt"')
        expect(gun.prepare(own.to("a@x.test").text("x"), "s@x.test")).equals(
            { "from": "s@x.test", "to": ["a@x.test"], "text": "x" },
        )

        denied = Mailgun("bad", "mg.x.test", transport=net.mocked(recorder([], { "message": "Forbidden" }, 401)))

        own.register(denied)

        refused = own.to("a@x.test").text("x").via(denied.name)

        await test.rejects(refused.send(), Code.UNAUTHORIZED, "mail.mailgun.send.key")

        with test.fails(Code.INTERNAL, "mail.mailgun.config.domain"): Mailgun("k", "")

@pytest.mark.anyio
class TestSms:

    async def test_sms_channels_share_the_dsl_and_declare_what_they_carry ( self ) -> None:

        seen: list[Ask] = []
        own  = Sms()
        log  = LogTexter()

        own.setup("Engine", log)

        local   = "\u0660\u0661\u0660\u0660\u0660\u0660"
        receipt = await own.to("+20 100 000 0000", local).text("code 1234").tag("otp").send()

        last = log.last()

        expect((receipt.status, receipt.to, last.body if last else None)).equals(
            ("logged", ("+20 100 000 0000", local), "code 1234"),
        )
        expect((phone("+20 100-000-0000"), phone("0020100"), phone("\u0660\u0661\u0660\u0662\u0663"))).equals(
            ("+201000000000", "+20100", "01023"),
        )

        twilio = Twilio("AC1", "tok", "+15550001", transport=net.mocked(recorder(seen, { "sid": "SM1" })))
        meta   = WhatsApp("wa-token", "1099", transport=net.mocked(recorder(seen, { "messages": [{ "id": "w.1" }] })))
        reply  = { "ok": True, "result": { "message_id": 77 } }
        bot    = Telegram("123:abc", transport=net.mocked(recorder(seen, reply)))

        for channel in (twilio, meta, bot): own.register(channel)

        sent = await own.to("+201000000000").text("hello").media("https://x.test/a.png").via("twilio").send()
        posted = parse_qs(seen[-1].body.decode())
        form   = { key: values[0] if len(values) == 1 else values for key, values in posted.items() }

        expect((sent.id, form, urlsplit(seen[-1].url).path)).equals((
            "SM1", { "To": "+201000000000", "Body": "hello", "From": "+15550001", "MediaUrl": "https://x.test/a.png" },
            "/2010-04-01/Accounts/AC1/Messages.json",
        ))

        await own.to("+201000000000").template("otp_code", "ar", "1234").via("whatsapp").send()

        expect((urlsplit(seen[-1].url).path, seen[-1].headers["authorization"], json.loads(seen[-1].body))).equals((
            "/v26.0/1099/messages", "Bearer wa-token",
            {
                "messaging_product": "whatsapp", "recipient_type": "individual", "to": "201000000000",
                "type": "template",
                "template": {
                    "name": "otp_code", "language": { "policy": "deterministic", "code": "ar" },
                    "components": [{ "type": "body", "parameters": [{ "type": "text", "text": "1234" }] }],
                },
            },
        ))

        heard = await own.to("-100200300").text("hi").quietly().via("telegram").send()

        expect((heard.id, urlsplit(seen[-1].url).path, json.loads(seen[-1].body))).equals((
            "77", "/bot123:abc/sendMessage",
            {
                "chat_id": "-100200300", "text": "hi", "link_preview_options": { "is_disabled": True },
                "disable_notification": True,
            },
        ))
        expect(own.describe()["capabilities"]).subset({ "telegram": ["media", "silent", "text"] })

        with test.fails(Code.INTERNAL, "sms.telegram.unsupported.template"):
            await own.to("1").template("x").via("telegram").send()
        with test.fails(Code.INTERNAL, "sms.telegram.unsupported.sender"):
            await own.to("1").text("x").from_("Engine").via("telegram").send()
        with test.fails(Code.INTERNAL, "sms.twilio.unsupported.template"):
            await own.to("1").template("x").via("twilio").send()
        with test.fails(Code.BAD_REQUEST, "sms.body"): await own.to("1").send()
        with test.fails(Code.BAD_REQUEST, "sms.to"): await own.draft("x").send()
