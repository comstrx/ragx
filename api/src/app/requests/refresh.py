from core.validate import Shape, field

class RefreshRequest(Shape):

    refresh_token: str = field(min_length=16, max_length=4096)
