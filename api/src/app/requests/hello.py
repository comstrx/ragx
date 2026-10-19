from core.validate import Shape, field

class HelloRequest(Shape):

    name: str = field("World", min_length=1, max_length=32, pattern=r"^[\w .'-]+$")
