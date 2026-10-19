from core import event

class Event(event.Event):

    async def dispatch ( self ) -> int:

        return await event.events.dispatch(self)
