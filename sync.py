"""Auto-sync scheduler: periodically re-index channels in the background.

Uses APScheduler's AsyncIOScheduler when available (bound to the app's
persistent asyncio loop); falls back to a small hand-rolled asyncio interval
loop if apscheduler isn't installed, so auto-sync still works without the
extra dependency.
"""

import asyncio
from typing import Awaitable, Callable, Dict

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    _HAVE_APSCHEDULER = True
except ImportError:
    _HAVE_APSCHEDULER = False


class SyncScheduler:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self._scheduler = AsyncIOScheduler(event_loop=loop) if _HAVE_APSCHEDULER else None
        self._fallback_futures: Dict[str, "asyncio.futures.Future"] = {}
        self._started = False

    def start(self) -> None:
        if self._scheduler and not self._started:
            self._scheduler.start()
        self._started = True

    def schedule(self, job_id: str, coro_factory: Callable[[], Awaitable[None]],
                 interval_minutes: int) -> None:
        """Run coro_factory() every interval_minutes, starting one interval
        from now. Replaces any existing job with the same job_id."""
        self.unschedule(job_id)
        if self._scheduler:
            self._scheduler.add_job(
                lambda: asyncio.ensure_future(coro_factory(), loop=self.loop),
                "interval", minutes=interval_minutes, id=job_id, replace_existing=True,
            )
        else:
            async def _loop():
                while True:
                    await asyncio.sleep(interval_minutes * 60)
                    try:
                        await coro_factory()
                    except Exception:
                        pass
            fut = asyncio.run_coroutine_threadsafe(_loop(), self.loop)
            self._fallback_futures[job_id] = fut

    def unschedule(self, job_id: str) -> None:
        if self._scheduler:
            try:
                self._scheduler.remove_job(job_id)
            except Exception:
                pass
        fut = self._fallback_futures.pop(job_id, None)
        if fut:
            fut.cancel()

    def list_job_ids(self) -> list:
        if self._scheduler:
            return [j.id for j in self._scheduler.get_jobs()]
        return list(self._fallback_futures.keys())

    def shutdown(self) -> None:
        if self._scheduler and self._started:
            try:
                self._scheduler.shutdown(wait=False)
            except Exception:
                pass
        for fut in self._fallback_futures.values():
            fut.cancel()
        self._fallback_futures.clear()
