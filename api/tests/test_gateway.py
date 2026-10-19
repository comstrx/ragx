from collections.abc import Callable, Mapping
from urllib.parse import parse_qs, urlsplit

from core.crypto import crypto
from core.date import date
from core.error import Code
from core.gateway import Credentials, Payments, Payout, Sandbox, Status, gateway
from core.json import json
from core.net import Answer, Ask, net
from core.number import Money
from core.test import expect, test
import pytest

type Handler = Callable[[Ask], Answer]

def wire ( routes: Mapping[tuple[str, str], Handler], seen: list[Ask] ) -> Callable[[Ask], Answer]:

    def answer ( asked: Ask ) -> Answer:

        seen.append(asked)

        handler = routes.get((asked.method, urlsplit(asked.url).path))

        if handler is None: return 404, b'{"message": "no route"}', { "content-type": "application/json" }

        return handler(asked)

    return answer

def reply ( payload: object, status: int = 200, **headers: str ) -> Answer:

    return status, json.encode(payload), { "content-type": "application/json", **headers }

def form_of ( asked: Ask ) -> dict[str, str]:

    return { key: values[0] for key, values in parse_qs(asked.body.decode()).items() }

@pytest.mark.anyio
class TestSandbox:

    async def test_the_sandbox_runs_every_capability_with_dense_results ( self ) -> None:

        own = Payments()
        box = Sandbox()

        own.register(box)

        start  = own.charge("100.00", "SAR", "order-1").customer("Ann", "ann@x.test")
        hosted = await start.returns("https://x.test/ok").deposit()

        expect((hosted.status, hosted.redirect_url, hosted.reference)).equals(
            (Status.ACTION, f"https://sandbox.local/pay/{hosted.id}", "order-1"),
        )

        paid = box.pay(hosted.id)

        expect(paid.dump()).subset({
            "status": "paid", "currency": "SAR", "card_last4": "4242", "amount": { "amount": "100.00", "minor": 10000 },
            "fee_amount": { "amount": "3.20" }, "net_amount": { "amount": "96.80" },
            "gross_amount": { "amount": "100.00" },
        })
        expect(paid.dump()).lacks("raw")

        part = await own.refund(hosted.id, Money.of("40", "SAR"), "damaged", idempotency="refund-1")
        same = await own.refund(hosted.id, Money.of("40", "SAR"), idempotency="refund-1")

        expect((part.kind.value, part.parent_id, same.id, (await own.find(hosted.id)).status)).equals(
            ("refund", hosted.id, part.id, Status.PARTIALLY_REFUNDED),
        )

        await own.refund(hosted.id)

        whole = await own.find(hosted.id)

        expect((whole.refunded_amount, whole.status)).equals((Money.of("100", "SAR"), Status.REFUNDED))

        held = await own.charge(50, "EGP", "order-2").authorize().deposit()

        expect(held.status).is_(Status.AUTHORIZED)
        expect((await own.capture(held.id, Money.of(30, "EGP"))).captured_amount).equals(Money.of(30, "EGP"))

        voided = await own.charge(5, "USD", "order-3").authorize().deposit()

        expect((await own.reject(voided.id)).status).is_(Status.VOIDED)

        open_  = await own.charge(5, "USD", "order-4").returns("https://x.test").deposit()
        closed = await own.cancel(open_.id)
        failed = await own.charge(5, "USD", "decline-5").deposit()
        twice  = await own.charge(9, "USD", "order-6").idempotent("pay-6").deposit()

        expect((closed.status, failed.status, failed.error_code)).equals(
            (Status.CANCELLED, Status.FAILED, "card_declined"),
        )
        expect((await own.charge(9, "USD", "order-6").idempotent("pay-6").deposit()).id).equals(twice.id)
        payout = Payout(amount=Money.of(20, "USD"), reference="p-1", recipient="ann@x.test")

        expect((await own.withdraw(payout)).kind.value).equals("payout")
        expect((await own.transfer(Money.of(7, "USD"), "acct_1", "t-1")).status).is_(Status.PAID)

        with test.fails(Code.CONFLICT, "gateway.sandbox.refund.state"): await own.refund(open_.id)
        with test.fails(Code.CONFLICT, "gateway.sandbox.capture.state"): await own.capture(hosted.id)
        with test.fails(Code.NOT_FOUND, "gateway.sandbox.find"): await own.find("sb_missing")

        body   = json.encode({ "id": "evt_1", "type": "payment.paid", "transaction": hosted.id })
        notice = await own.webhook(body, box.sign(body))

        expect((notice.type, notice.transaction.id if notice.transaction else None)).equals(("payment.paid", hosted.id))

        with test.fails(Code.UNAUTHORIZED, "gateway.sandbox.webhook.signature"):
            await own.webhook(body, { "x-sandbox-signature": "0" * 64 })

    async def test_capabilities_are_declared_and_refused_explicitly ( self ) -> None:

        own = Payments()

        own.connect("paytabs", { "secret_key": "server", "form_id": "77", "region": "SAU" }, default=True)
        own.connect("stripe", Credentials(secret_key="sk_test"))

        expect(own.describe()["capabilities"]["paytabs"]).equals(
            ["capture", "deposit", "find", "refund", "void", "webhook"],
        )
        expect((own.which("withdraw"), own.supports("transfer"), own.supports("transfer", "stripe"))).equals(
            (["stripe"], False, True),
        )

        with test.fails(Code.INTERNAL, "gateway.paytabs.unsupported.withdraw"):
            await own.withdraw(Payout(amount=Money.of(1, "SAR"), reference="r", recipient="x"))
        with test.fails(Code.INTERNAL, "gateway.paytabs.config.form_id"): own.build("paytabs", { "secret_key": "s" })
        with test.fails(Code.INTERNAL, "gateway.ghost.missing"): own.build("ghost", {})
        with test.fails(Code.INTERNAL, "gateway.nope.missing"): own.use("nope")

        expect(gateway.family()).equals("gateway")

@pytest.mark.anyio
class TestProviders:

    async def test_stripe_speaks_form_wire_signs_webhooks_and_never_repeats_payments ( self ) -> None:

        seen: list[Ask] = []
        hits = { "post": 0, "get": 0 }

        def session ( asked: Ask ) -> Answer:

            return reply({
                "id": "cs_1", "object": "checkout.session", "url": "https://checkout.stripe.test/cs_1",
                "status": "open",
                "payment_status": "unpaid", "amount_total": 1050, "currency": "sar", "client_reference_id": "o-9",
            })

        def flaky ( asked: Ask ) -> Answer:

            hits["post" if asked.method == "POST" else "get"] += 1

            return reply({ "error": { "message": "boom" } }, 500)

        def intent ( asked: Ask ) -> Answer:

            return reply({
                "id": "pi_1", "object": "payment_intent", "status": "succeeded", "amount": 1050,
                "amount_received": 1050,
                "currency": "sar", "metadata": { "reference": "o-9" },
                "latest_charge": {
                    "amount_refunded": 0, "payment_method_details": { "card": { "brand": "mada", "last4": "1111" } },
                    "balance_transaction": { "amount": 1050, "fee": 61, "net": 989 },
                },
            })

        routes = {
            ("POST", "/v1/checkout/sessions"): session, ("GET", "/v1/payment_intents/pi_1"): intent,
            ("POST", "/v1/refunds"): lambda asked: reply({ "error": { "message": "Charge already refunded" } }, 400),
            ("POST", "/v1/payouts"): lambda asked: reply({ "error": { "message": "bad key" } }, 401),
            ("POST", "/v1/transfers"): lambda asked: reply(
                { "error": { "message": "slow down" } }, 429, **{ "retry-after": "0" },
            ),
            ("POST", "/v1/payment_intents"): flaky, ("GET", "/v1/refunds/re_1"): flaky,
        }
        secret = "whsec_unit"
        keys   = { "secret_key": "sk_test_1", "webhook_secret": secret }
        stripe = gateway.build("stripe", keys, net.mocked(wire(routes, seen)))
        made   = await stripe.deposit(
            gateway.charge("10.50", "SAR", "o-9").returns("https://x.test/ok").idempotent("dep-1").payment(),
        )
        sent   = form_of(seen[0])

        expect((made.id, made.redirect_url, made.status, made.amount.minor())).equals(
            ("cs_1", "https://checkout.stripe.test/cs_1", Status.ACTION, 1050),
        )
        expect(sent).subset({
            "mode": "payment", "line_items[0][price_data][unit_amount]": "1050",
            "line_items[0][price_data][currency]": "sar",
            "success_url": "https://x.test/ok", "client_reference_id": "o-9", "metadata[reference]": "o-9",
            "payment_intent_data[capture_method]": "automatic",
        })
        expect(seen[0].headers).subset({ "authorization": "Bearer sk_test_1", "idempotency-key": "dep-1" })

        found = await stripe.find("pi_1")

        expect((found.status, found.fee_amount, found.net_amount, found.card_brand, found.reference)).equals(
            (Status.PAID, Money.minor_of(61, "SAR"), Money.minor_of(989, "SAR"), "mada", "o-9"),
        )

        await test.rejects(stripe.refund("pi_1"), Code.BAD_REQUEST, "gateway.stripe.refund.request")
        refused = Payout(amount=Money.of(1, "SAR"), reference="x", recipient="y")

        await test.rejects(stripe.withdraw(refused), Code.UNAUTHORIZED)

        limited = await test.rejects(stripe.transfer(Money.of(1, "SAR"), "acct_9"), Code.TOO_MANY_REQUESTS)

        expect(limited.message).equals("slow down")

        await test.rejects(stripe.deposit(gateway.charge(1, "SAR", "o-1").payment()), Code.UNAVAILABLE)
        await test.rejects(stripe.find("re_1"), Code.UNAVAILABLE)

        expect(hits).equals({ "post": 1, "get": 3 })

        inner = json.loads(intent(seen[0])[1])
        body  = json.encode({ "id": "evt_1", "type": "payment_intent.succeeded", "data": { "object": inner } })
        stamp = str(int(date.stamp()))
        good  = crypto.sign(f"{stamp}.".encode() + body, secret)

        notice = await stripe.webhook(body, { "Stripe-Signature": f"t={stamp},v1={good}" })

        expect((notice.type, notice.transaction.status if notice.transaction else None)).equals(
            ("payment_intent.succeeded", Status.PAID),
        )

        await test.rejects(stripe.webhook(body, { "Stripe-Signature": f"t={stamp},v1={'0' * 64}" }), Code.UNAUTHORIZED)
        stale = { "Stripe-Signature": f"t=1,v1={good}" }

        await test.rejects(stripe.webhook(body, stale), Code.UNAUTHORIZED, "gateway.stripe.webhook.stale")
        await stripe.close()

    async def test_paypal_paytabs_and_paymob_map_their_own_wires_to_one_contract ( self ) -> None:

        seen: list[Ask] = []
        order = {
            "id": "ORDER-1", "status": "PAYER_ACTION_REQUIRED",
            "purchase_units": [{ "reference_id": "o-1", "amount": { "currency_code": "USD", "value": "12.00" } }],
            "links": [{ "rel": "payer-action", "href": "https://paypal.test/approve" }],
        }
        done  = {
            "id": "ORDER-1", "status": "COMPLETED",
            "purchase_units": [{ "reference_id": "o-1", "payments": { "captures": [{
                "id": "CAP-1", "status": "COMPLETED", "amount": { "currency_code": "USD", "value": "12.00" },
                "seller_receivable_breakdown": {
                    "gross_amount": { "value": "12.00" }, "paypal_fee": { "value": "0.65" },
                    "net_amount": { "value": "11.35" },
                },
            }] } }],
        }
        mobbed = {
            "id": 991, "amount_cents": 15050, "currency": "EGP", "success": True, "pending": False,
            "order": { "id": 55, "merchant_order_id": "o-3" }, "source_data": { "pan": "2346", "type": "card" },
        }
        routes = {
            ("POST", "/v1/oauth2/token"): lambda asked: reply({ "access_token": "A21", "expires_in": 3600 }),
            ("POST", "/v2/checkout/orders"): lambda asked: reply(order, 201),
            ("GET", "/v2/checkout/orders/ORDER-1"): lambda asked: reply(order),
            ("POST", "/v2/checkout/orders/ORDER-1/capture"): lambda asked: reply(done, 201),
            ("POST", "/v1/notifications/verify-webhook-signature"): lambda asked: reply(
                { "verification_status": "SUCCESS" },
            ),
            ("POST", "/payment/request"): lambda asked: reply({
                "tran_ref": "TST2", "cart_id": "o-2", "cart_currency": "SAR", "cart_amount": "20.00",
                "redirect_url": "https://secure.paytabs.sa/payment/page/x", "tran_type": "Sale",
            }),
            ("POST", "/v1/intention/"): lambda asked: reply({ "id": "pi_eg_1", "client_secret": "egy_csk_1" }, 201),
            ("POST", "/api/auth/tokens"): lambda asked: reply({ "token": "auth-1" }, 201),
            ("GET", "/api/acceptance/transactions/991"): lambda asked: reply(mobbed),
            ("POST", "/api/acceptance/void_refund/refund"): lambda asked: reply({ **mobbed, "id": 992 }),
            ("POST", "/api/acceptance/void_refund/void"): lambda asked: reply({ **mobbed, "id": 993 }),
        }
        transport = net.mocked(wire(routes, seen))
        keys      = { "client_id": "cid", "secret_key": "sec", "webhook_id": "WH-1", "sandbox": True }
        paypal    = gateway.build("paypal", keys, transport)
        charge    = gateway.charge("12", "USD", "o-1").returns("https://x.test/ok").idempotent("k-1")
        approve   = await paypal.deposit(charge.payment())
        captured  = await paypal.capture("ORDER-1")

        expect((approve.redirect_url, approve.status, captured.status)).equals(
            ("https://paypal.test/approve", Status.ACTION, Status.PAID),
        )
        expect((captured.fee_amount, captured.net_amount)).equals((Money.of("0.65", "USD"), Money.of("11.35", "USD")))
        expect([asked.url.split("/", 3)[-1] for asked in seen].count("v1/oauth2/token")).equals(1)
        unit = { "reference_id": "o-1", "custom_id": "o-1", "amount": { "currency_code": "USD", "value": "12.00" } }

        units = [{ **unit, "description": "o-1" }]

        expect(json.loads(seen[1].body)).subset({ "intent": "CAPTURE", "purchase_units": units })
        expect(seen[1].headers).subset({ "paypal-request-id": "k-1", "authorization": "Bearer A21" })

        signed = {
            "paypal-auth-algo": "SHA256withRSA", "paypal-cert-url": "https://cert", "paypal-transmission-id": "t1",
            "paypal-transmission-sig": "sig", "paypal-transmission-time": "now",
        }
        event  = json.encode({ "id": "WH-EVT", "event_type": "CHECKOUT.ORDER.APPROVED", "resource": order })

        expect((await paypal.webhook(event, signed)).type).equals("CHECKOUT.ORDER.APPROVED")

        await test.rejects(paypal.webhook(event, {}), Code.UNAUTHORIZED, "gateway.paypal.webhook.signature")

        tabs = gateway.build("paytabs", { "secret_key": "SK-1", "form_id": "77", "region": "sau" }, transport)
        page = await tabs.deposit(gateway.charge(20, "SAR", "o-2").notify("https://x.test/hook").payment())

        expect((page.id, page.status, page.redirect_url, json.loads(seen[-1].body)["profile_id"])).equals(
            ("TST2", Status.ACTION, "https://secure.paytabs.sa/payment/page/x", 77),
        )
        expect(seen[-1].headers["authorization"]).equals("SK-1")

        sent = json.loads(seen[-1].body)

        expect(sent).subset({ "callback": "https://x.test/hook" }).lacks("return", "customer_details")

        callback = json.encode({
            "tran_ref": "TST2", "cart_id": "o-2", "cart_currency": "SAR", "cart_amount": "20.00", "tran_type": "Sale",
            "payment_result": { "response_status": "A", "response_code": "G1", "response_message": "Authorised" },
            "payment_info": { "card_scheme": "Visa", "payment_description": "4111 11## #### 1111" },
        })
        heard    = await tabs.webhook(callback, { "Signature": crypto.sign(callback, "SK-1") })

        expect(heard.transaction.dump() if heard.transaction else {}).subset({ "status": "paid", "card_last4": "1111" })

        await test.rejects(tabs.webhook(callback, { "signature": "x" }), Code.UNAUTHORIZED)

        keys  = { "secret_key": "sk", "public_key": "pk", "form_id": "123, 456", "webhook_secret": "hm" }
        mob   = gateway.build("paymob", keys, transport)
        going = await mob.deposit(gateway.charge("150.5", "EGP", "o-3").customer("Ann Lee", "ann@x.test").payment())

        sent = json.loads(seen[-1].body)

        expect((going.redirect_url, sent["payment_methods"], sent["amount"])).equals(
            ("https://accept.paymob.com/unifiedcheckout/?publicKey=pk&clientSecret=egy_csk_1", [123, 456], 15050),
        )
        expect(seen[-1].headers["authorization"]).equals("Token sk")

        obj = {
            "id": 991, "amount_cents": 15050, "created_at": "2026-10-19T10:00:00", "currency": "EGP",
            "error_occured": False,
            "has_parent_transaction": False, "integration_id": 123, "is_3d_secure": True, "is_auth": False,
            "is_capture": False, "is_refunded": False, "is_standalone_payment": True, "is_voided": False,
            "order": { "id": 55, "merchant_order_id": "o-3" }, "owner": 7, "pending": False,
            "source_data": { "pan": "2346", "sub_type": "MasterCard", "type": "card" }, "success": True,
        }
        fields = (
            "15050", "2026-10-19T10:00:00", "EGP", "false", "false", "991", "123", "true", "false", "false", "false",
            "true", "false", "55", "7", "false", "2346", "MasterCard", "card", "true",
        )
        body   = json.encode({ "type": "TRANSACTION", "obj": obj })
        sealed = crypto.sign("".join(fields), "hm", "sha512")
        paid   = await mob.webhook(body, {}, { "hmac": sealed })

        expect(paid.transaction.dump() if paid.transaction else {}).subset({
            "id": "991", "status": "paid", "reference": "o-3", "card_last4": "2346", "amount": { "minor": 15050 },
        })

        await test.rejects(mob.webhook(body, {}, { "hmac": sealed[:-1] + "0" }), Code.UNAUTHORIZED)
        await test.rejects(mob.find("991"), Code.INTERNAL, "gateway.paymob.config.api_key")

        mob      = gateway.build("paymob", { **keys, "api_key": "ak" }, transport)
        found    = await mob.find("991")
        inquiry  = seen[-1]
        login    = seen[-2]
        returned = await mob.refund("991")
        refunded = seen[-1]

        await mob.void("991")
        await mob.find("991")

        expect((found.id, found.amount.minor(), returned.id)).equals(("991", 15050, "992"))
        expect((json.loads(login.body), "authorization" in login.headers)).equals(({ "api_key": "ak" }, False))
        expect((inquiry.headers["authorization"], refunded.headers["authorization"])).equals(
            ("Bearer auth-1", "Token sk"),
        )
        expect(json.loads(refunded.body)).equals({ "transaction_id": 991, "amount_cents": 15050 })
        expect(json.loads(seen[-2].body)).equals({ "transaction_id": 991 })
        expect([asked.url.endswith("/api/auth/tokens") for asked in seen].count(True)).equals(1)
