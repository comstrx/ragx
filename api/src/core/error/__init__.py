from .code import Code
from .fault import Errors, Fault
from .faults import Faults

error = Faults()

__all__ = ["Code", "Errors", "Fault", "Faults", "error"]
