from core.validate import Email, Password, Shape

class LoginRequest(Shape):

    email    : Email
    password : Password
