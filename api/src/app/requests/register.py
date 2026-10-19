from core.validate import Email, Name, Password, Shape

class RegisterRequest(Shape):

    name     : Name
    email    : Email
    password : Password
