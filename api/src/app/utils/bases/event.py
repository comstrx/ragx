from core.event import Event, events

class BaseEvent(Event):

    async def dispatch ( self ) -> int:
        return await events.dispatch(self)
