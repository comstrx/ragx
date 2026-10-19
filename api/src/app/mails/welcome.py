from core.queue import Queued
from app.utils.cycle import Mail

class WelcomeMail(Mail, Queued):

    subject = "Welcome to {app}, {name}"
    html    = "mail/welcome.html"
    text    = "mail/welcome.txt"
