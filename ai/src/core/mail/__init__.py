from .mail import Mail
from .message import Attachment, Message
from .transport import LogTransport, MemoryTransport, SmtpTransport, Transport

mail = Mail()

__all__ = ["Attachment", "LogTransport", "Mail", "MemoryTransport", "Message", "SmtpTransport", "Transport", "mail"]
