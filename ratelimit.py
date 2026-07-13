"""Shared FloodWait backoff so concurrent downloads/uploads cooperate instead
of each independently hammering Telegram and tripping its own wait.

Create one FloodWaitGate per connected client and pass it into every
downloader function; whichever coroutine hits a FloodWaitError first trips
the gate, and every other coroutine sharing it (running concurrently, or
started moments later) waits out the same cooldown before its next call.
"""

import asyncio
import time
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")


class FloodWaitGate:
    def __init__(self) -> None:
        self._resume_at = 0.0
        self._lock = asyncio.Lock()

    async def wait_if_tripped(self) -> None:
        while True:
            async with self._lock:
                remaining = self._resume_at - time.monotonic()
            if remaining <= 0:
                return
            await asyncio.sleep(remaining)

    async def trip(self, seconds: float) -> None:
        async with self._lock:
            self._resume_at = max(self._resume_at, time.monotonic() + seconds)

    async def run(self, fn: Callable[..., Awaitable[T]], *args: Any,
                   max_attempts: int = 3, **kwargs: Any) -> T:
        """Call fn(*args, **kwargs), retrying on FloodWaitError while
        cooperating with every other caller sharing this gate. Non-FloodWait
        exceptions propagate immediately (callers keep their own retry logic
        for transient errors)."""
        from telethon import errors

        last_exc: Exception = RuntimeError("FloodWaitGate.run: no attempts made")
        for attempt in range(max_attempts):
            await self.wait_if_tripped()
            try:
                return await fn(*args, **kwargs)
            except errors.FloodWaitError as e:
                last_exc = e
                await self.trip(e.seconds + 1)
                if attempt == max_attempts - 1:
                    raise
        raise last_exc
