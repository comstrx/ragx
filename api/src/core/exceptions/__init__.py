from .code import Code
from .fault import Errors, Fault
from .faults import Faults
from .handler import Exceptions, Handler

exceptions = Exceptions()

__all__ = ["Code", "Errors", "Exceptions", "Fault", "Faults", "Handler", "exceptions"]
