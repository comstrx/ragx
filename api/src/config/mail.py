from typing import ClassVar, Literal

from core.config import Settings, field

type Driver = Literal["log", "mailgun"]

class MailConfig(Settings, env_prefix="MAIL_"):

    hidden: ClassVar[tuple[str, ...]] = ("mailgun_key",)

    driver         : Driver = "log"
    sender         : str    = "hello@ragx.test"
    name           : str    = "RagX"
    timeout        : float  = field(20.0, gt=0, le=120)
    mailgun_key    : str    = ""
    mailgun_domain : str    = ""
    mailgun_region : str    = "us"
