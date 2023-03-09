from __future__ import annotations

import asyncio
import pytest

from typing import Any, Optional, AsyncGenerator, cast


class ClockedTest:
    """
    A context wrapper around an event loop that allows tests to advance the
    clock which is inspired by the ClockedTestCase of the asynctest library (no
    longer receiving updates for Python 3.8+).
    """

    time: float = 0.0

    def __init__(self, loop: asyncio.BaseEventLoop) -> None:
        self.loop = loop

    def __enter__(self) -> ClockedTest:
        # incorporate offset timing into the event loop
        self._original_time_fn = self.loop.time
        self.loop.time = lambda: self.time  # type: ignore[assignment]
        return self

    def __exit__(self, *_: Any, **__: Any) -> None:
        # restore the loop time function
        self.loop.time = self._original_time_fn  # type: ignore[assignment]

    async def __call__(self, seconds: float) -> None:
        await self.advance(seconds)

    async def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("Advance time must not be negative")
        await self._drain_loop()

        target_time = self.time + seconds
        while True:
            next_time = self._next_scheduled()
            if next_time is None or next_time > target_time:
                break

            self.time = next_time
            await self._drain_loop()

        self.time = target_time
        await self._drain_loop()

    def _next_scheduled(self) -> Optional[float]:
        try:
            return cast(float, self.loop._scheduled[0]._when)  # type: ignore[attr-defined]
        except IndexError:
            return None

    async def _drain_loop(self) -> None:
        while True:
            next_time = self._next_scheduled()
            if not self.loop._ready and (  # type: ignore[attr-defined]
                next_time is None or next_time > self.time
            ):
                break
            await asyncio.sleep(0)


@pytest.fixture(scope="function")
async def clocked_test(
    event_loop: asyncio.BaseEventLoop,
) -> AsyncGenerator[ClockedTest, None]:
    """
    This function scoped fixture returns an instance of a ClockedTest.
    """
    with ClockedTest(event_loop) as clocked_test:
        yield clocked_test
