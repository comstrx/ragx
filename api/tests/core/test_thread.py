from core.thread import thread
import asyncio, pytest


@pytest.mark.anyio
class TestThread:

    async def test_gather_keeps_order_and_honors_the_limit ( self ) -> None:

        running = 0
        peak    = 0

        async def job ( value: int ) -> int:

            nonlocal running, peak

            running += 1
            peak     = max(peak, running)

            await asyncio.sleep(0.01)

            running -= 1

            return value * 2

        assert await thread.gather(job(1), job(2), job(3), limit=2) == [2, 4, 6]
        assert peak == 2

    async def test_retry_backs_off_then_gives_up ( self ) -> None:

        calls = 0

        async def flaky () -> str:

            nonlocal calls

            calls += 1

            if calls < 3: raise ConnectionError(calls)

            return "ok"

        assert await thread.retry(flaky, times=3, delay=0.001) == "ok"
        assert calls == 3

        async def broken () -> None:
            raise ValueError("never")

        with pytest.raises(ValueError, match="never"): await thread.retry(broken, times=2, delay=0.001)

    async def test_timeout_offload_and_once ( self ) -> None:

        with pytest.raises(TimeoutError): await thread.timeout(asyncio.sleep(1), 0.01)

        assert await thread.offload(sum, [1, 2, 3]) == 6

        seen = 0

        async def expensive () -> int:

            nonlocal seen

            seen += 1

            return seen

        cached = thread.once(expensive)

        assert await thread.gather(cached(), cached(), cached()) == [1, 1, 1]
