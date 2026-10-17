from core.validate import Email, Password
from app.utils.bases import BaseRequest

class LoginRequest(BaseRequest):

    email    : Email
    password : Password
