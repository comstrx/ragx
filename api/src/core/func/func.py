from .call import Call
from .guard import Guard
from .limit import Limit
from .measure import Measure
from .memo import Memo
from .retry import Retry

class Func(Call, Guard, Memo, Retry, Limit, Measure):

    __slots__ = ()
