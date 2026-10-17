from core.queue import Queued
from app.utils.bases import BaseMail

class WelcomeMail(BaseMail, Queued):

    subject = "Welcome to {app}, {name}"
    html    = "mail/welcome.html"
    text    = "mail/welcome.txt"
