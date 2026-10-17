from core.validate import Email, Name, Password
from app.utils.bases import BaseRequest

class RegisterRequest(BaseRequest):

    name     : Name
    email    : Email
    password : Password
