from engine.domain import Domains
from engine.gateway import Payments, Payout, Status
from engine.mail import Mail, Mailgun
from engine.number import Money
from engine.rand import rand
from engine.test import expect
import os, pytest

def given ( *names: str ) -> list[str]:

    found = [os.environ.get(name, "") for name in names]

    if not all(found): pytest.skip(f"set {' '.join(names)} to exercise this provider live")

    return found

def refuse ( condition: bool, why: str ) -> None:

    if condition: pytest.skip(why)

class TestLiveProviders:

    async def test_stripe_test_mode_opens_and_finds_a_checkout ( self ) -> None:

        (key,) = given("LIVE_STRIPE_TEST_KEY")

        refuse(not key.startswith("sk_test_"), "only a Stripe test key may run here")

        own = Payments()

        own.connect("stripe", { "secret_key": key })

        try:

            opened = await own.charge("1.00", "USD", f"live-{rand.hex(4)}").returns("https://example.com/done").deposit()
            found  = await own.find(opened.id)

            expect((found.id, found.provider)).equals((opened.id, "stripe"))
            expect(opened.status).is_(Status.ACTION)
            expect(opened.redirect_url).some().starts_with("https://")

        finally:

            await own.close()

    async def test_every_stripe_verb_speaks_the_official_spec_through_stripe_mock ( self ) -> None:

        (base,) = given("LIVE_STRIPE_MOCK_URL")
        own     = Payments()

        own.connect("stripe", { "secret_key": "sk_test_123", "base_url": base })

        try:

            hosted  = await own.charge("10.00", "USD", "o-1").returns("https://example.com/done").deposit()
            direct  = await own.charge("10.00", "USD", "o-2").customer("Ann", "ann@example.com").authorize().deposit()
            found   = await own.find(direct.id)
            session = await own.find(hosted.id)
            taken   = await own.capture(direct.id, Money.of("10.00", "USD"))
            back    = await own.refund(direct.id, Money.of("4.00", "USD"), "requested_by_customer")
            voided  = await own.void(direct.id)
            expired = await own.cancel(hosted.id)
            paid    = await own.withdraw(Payout(amount=Money.of("5.00", "USD"), reference="w-1", recipient="ba_123"))
            moved   = await own.transfer(Money.of("3.00", "USD"), "acct_123", "t-1")
            kinds   = [found.provider, session.provider, taken.provider, back.provider, voided.provider]

            expect([*kinds, expired.provider, paid.provider, moved.provider]).each(lambda name: name == "stripe")
            expect([hosted.id[:3], direct.id[:3], back.id[:3], paid.id[:3], moved.id[:3]]).equals(
                ["cs_", "pi_", "re_", "po_", "tr_"],
            )
            expect(hosted.redirect_url).some().starts_with("https://")

        finally:

            await own.close()

    async def test_paypal_sandbox_opens_an_order ( self ) -> None:

        client, secret = given("LIVE_PAYPAL_CLIENT_ID", "LIVE_PAYPAL_SECRET")
        own            = Payments()

        own.connect("paypal", { "client_id": client, "secret_key": secret, "sandbox": True })

        try:

            opened = await own.charge("1.00", "USD", f"live-{rand.hex(4)}").returns("https://example.com/done").deposit()

            expect((opened.provider, opened.status)).equals(("paypal", Status.ACTION))
            expect(opened.redirect_url).some().contains("sandbox.paypal.com")

        finally:

            await own.close()

    async def test_paymob_test_mode_opens_a_unified_checkout ( self ) -> None:

        secret, public, methods = given("LIVE_PAYMOB_SECRET_KEY", "LIVE_PAYMOB_PUBLIC_KEY", "LIVE_PAYMOB_INTEGRATION")

        refuse("_sk_test_" not in secret, "only a Paymob test secret key may run here")

        own    = Payments()
        region = os.environ.get("LIVE_PAYMOB_REGION", "EGY")

        own.connect("paymob", { "secret_key": secret, "public_key": public, "form_id": methods, "region": region })

        try:

            buyer  = own.charge("10.00", "EGP", f"live-{rand.hex(4)}").customer("Ann Lee", "ann@example.com")
            opened = await buyer.returns("https://example.com/done").deposit()

            expect((opened.provider, opened.status)).equals(("paymob", Status.ACTION))
            expect((opened.id, opened.client_secret)).each(bool)
            expect(opened.redirect_url).some().contains("unifiedcheckout")

        finally:

            await own.close()

    async def test_paytabs_test_profile_opens_and_finds_a_hosted_page ( self ) -> None:

        server, profile = given("LIVE_PAYTABS_SERVER_KEY", "LIVE_PAYTABS_PROFILE_ID")
        own             = Payments()
        region          = os.environ.get("LIVE_PAYTABS_REGION", "EGY")
        currency        = os.environ.get("LIVE_PAYTABS_CURRENCY", "EGP")

        own.connect("paytabs", { "secret_key": server, "form_id": profile, "region": region })

        try:

            opened = await own.charge("10.00", currency, f"live-{rand.hex(4)}").returns("https://example.com/done").deposit()
            found  = await own.find(opened.id)

            expect((opened.provider, opened.status, found.id)).equals(("paytabs", Status.ACTION, opened.id))
            expect(opened.redirect_url).some().starts_with("https://secure")

        finally:

            await own.close()

    async def test_mailgun_sandbox_queues_a_message ( self ) -> None:

        key, domain, recipient = given("LIVE_MAILGUN_KEY", "LIVE_MAILGUN_DOMAIN", "LIVE_MAILGUN_TO")

        refuse(not domain.startswith("sandbox"), "only a Mailgun sandbox domain may run here")

        own = Mail()

        own.setup(f"engine@{domain}", "Engine", Mailgun(key, domain))

        try:

            receipt = await own.to(recipient).about("Engine live check").text("A live provider check.").send()

            expect(receipt.id).filled()
            expect(receipt.status).equals("queued")

        finally:

            await own.close()

    async def test_registrars_answer_availability_read_only ( self ) -> None:

        token, account = given("LIVE_CLOUDFLARE_TOKEN", "LIVE_CLOUDFLARE_ACCOUNT")
        own            = Domains()

        own.connect("cloudflare", token=token, account=account)

        try:

            found = await own.check(f"engine-live-{rand.hex(6)}.com")

            expect(found).length(1)
            expect(found[0].name).ends_with(".com")

        finally:

            await own.close()
