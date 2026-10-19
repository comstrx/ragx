from typing import override
from core.config import config
from core.error import Fault
from core.queue import Queued
from app.events import UserRegistered
from app.mails import WelcomeMail
from app.utils.cycle import Listener

class SendWelcomeMail(Listener, Queued):

    @override
    async def handle ( self, event: UserRegistered ) -> None:

        welcome = WelcomeMail(name=event.name, app=config.get("app.name", "RagX")).to(event.email)

        try: await welcome.send_now()
        except Fault as fault: self.log.warning("welcome.skipped", user=event.user_id, reason=fault.reason)
