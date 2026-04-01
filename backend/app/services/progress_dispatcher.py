import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, Callable, Awaitable

from ..models.enums import Step

logger = logging.getLogger(__name__)


@dataclass
class ProgressItem:
    step: Step
    percent: float
    message: str
    details: Dict[str, Any]
    epoch: int
    is_step_change: bool


class ProgressDispatcher:
    """Thread-safe, non-blocking progress notification dispatcher.

    Producers call notify() from any context (async or executor thread).
    A background drain loop on the event loop sends WebSocket messages.
    """

    def __init__(
        self,
        broadcast_progress: Callable[..., Awaitable],
        broadcast_step_change: Callable[..., Awaitable],
    ):
        self._queue: asyncio.Queue[ProgressItem] = asyncio.Queue()
        self._broadcast_progress = broadcast_progress
        self._broadcast_step_change = broadcast_step_change
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._drain_task: Optional[asyncio.Task] = None
        self._epoch: int = 0
        self._current_step: Optional[Step] = None
        # Throttle: minimum seconds between progress broadcasts (step changes bypass this)
        self._min_interval: float = 1 / 15
        self._last_send_time: float = 0.0

    @property
    def epoch(self) -> int:
        return self._epoch

    def increment_epoch(self):
        """Invalidate all in-flight callbacks from previous epoch."""
        self._epoch += 1
        self._current_step = None

    def start(self):
        """Start the drain loop. Must be called from the event loop thread."""
        if self._drain_task and not self._drain_task.done():
            return
        self._loop = asyncio.get_running_loop()
        self._drain_task = asyncio.create_task(self._drain_loop())

    async def stop(self):
        """Stop the drain loop."""
        if self._drain_task:
            self._drain_task.cancel()
            try:
                await self._drain_task
            except asyncio.CancelledError:
                pass
            self._drain_task = None

    def notify(
        self,
        step: Step,
        percent: float,
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
        epoch: Optional[int] = None,
    ):
        """Enqueue a progress notification. Safe to call from any thread.

        If epoch is provided and it doesn't match the current epoch, the
        notification is dropped immediately to prevent stale worker threads
        from corrupting step-change tracking.
        """
        effective_epoch = epoch if epoch is not None else self._epoch
        if effective_epoch != self._epoch:
            return

        is_step_change = step != self._current_step
        self._current_step = step

        item = ProgressItem(
            step=step,
            percent=percent,
            message=message or "",
            details=details or {},
            epoch=effective_epoch,
            is_step_change=is_step_change,
        )

        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._queue.put_nowait, item)
        else:
            logger.warning("ProgressDispatcher: event loop not running, dropping notification")

    def scoped_callback(self) -> Callable:
        """Return a plain callback bound to the current epoch.

        After increment_epoch(), any callbacks from a previous epoch
        become no-ops, preventing stale progress updates.
        """
        bound_epoch = self._epoch

        def callback(
            step: Step,
            percent: float,
            message: str = "",
            details: Optional[Dict[str, Any]] = None,
        ):
            self.notify(step, percent, message, details, epoch=bound_epoch)

        return callback

    async def _drain_loop(self):
        """Background task that drains the queue and sends WS messages.

        Progress-only updates are throttled to self._min_interval seconds
        between sends. Step changes and feed entries always send immediately.
        """
        while True:
            try:
                item = await self._queue.get()

                if item.epoch != self._epoch:
                    continue

                # Step changes and feed entries bypass throttling
                if item.is_step_change or item.details.get("feed_text"):
                    if item.is_step_change:
                        await self._broadcast_step_change(item.step)
                    await self._broadcast_progress(
                        item.step, item.percent, item.message, item.details
                    )
                    self._last_send_time = time.monotonic()
                    continue

                # Throttle progress-only updates
                now = time.monotonic()
                elapsed = now - self._last_send_time
                if elapsed < self._min_interval:
                    # Drain any newer items that arrived, keep the latest
                    latest = item
                    try:
                        while True:
                            latest = self._queue.get_nowait()
                            if latest.is_step_change or latest.epoch != self._epoch:
                                break
                            # Don't skip feed entries during drain
                            if latest.details.get("feed_text"):
                                await self._broadcast_progress(
                                    latest.step, latest.percent, latest.message, latest.details
                                )
                    except asyncio.QueueEmpty:
                        pass

                    # If we pulled a step change or stale item, handle it next iteration
                    if latest.is_step_change or latest.epoch != self._epoch:
                        await self._queue.put(latest)
                        continue

                    await asyncio.sleep(self._min_interval - elapsed)
                    item = latest

                await self._broadcast_progress(
                    item.step, item.percent, item.message, item.details
                )
                self._last_send_time = time.monotonic()

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error in progress drain loop")
