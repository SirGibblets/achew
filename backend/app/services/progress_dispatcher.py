import asyncio
import logging
import queue
import threading
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
    A dedicated background thread drains the input queue, applies
    throttling, and forwards items to a lightweight sender task on
    the main event loop. This architecture ensures that GIL contention
    from executor threads cannot stall progress delivery.
    """

    def __init__(
        self,
        broadcast_progress: Callable[..., Awaitable],
        broadcast_step_change: Callable[..., Awaitable],
    ):
        self._input_queue: queue.Queue[Optional[ProgressItem]] = queue.Queue()
        self._send_queue: Optional[asyncio.Queue] = None

        self._broadcast_progress = broadcast_progress
        self._broadcast_step_change = broadcast_step_change

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._sender_task: Optional[asyncio.Task] = None
        self._stop = threading.Event()

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
        """Start the dispatcher. Must be called from the event loop thread."""
        if self._thread and self._thread.is_alive():
            return
        self._loop = asyncio.get_running_loop()
        self._send_queue = asyncio.Queue()
        self._sender_task = asyncio.ensure_future(self._sender_loop())
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._drain_loop, daemon=True, name="progress-dispatcher",
        )
        self._thread.start()

    async def stop(self):
        """Stop the dispatcher."""
        self._stop.set()
        # Wake the drain thread so it can exit
        self._input_queue.put(None)
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        # Stop the sender task
        if self._sender_task:
            if self._send_queue:
                self._send_queue.put_nowait(None)
            try:
                await self._sender_task
            except asyncio.CancelledError:
                pass
            self._sender_task = None

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

        try:
            self._input_queue.put_nowait(item)
        except queue.Full:
            pass  # Unbounded queue; should never happen

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

    # ------------------------------------------------------------------
    # Drain thread -- runs independently of the main event loop / GIL
    # ------------------------------------------------------------------

    def _drain_loop(self):
        """Background thread that drains the input queue and feeds the send queue.

        Progress-only updates are throttled to self._min_interval seconds
        between sends. Step changes and feed entries always send immediately.
        """
        while not self._stop.is_set():
            try:
                try:
                    item = self._input_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                if item is None:
                    break  # Shutdown signal

                if item.epoch != self._epoch:
                    continue

                # Step changes and feed entries bypass throttling
                if item.is_step_change or item.details.get("feed_text"):
                    self._schedule_send(item)
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
                            latest = self._input_queue.get_nowait()
                            if latest is None:
                                return  # Shutdown
                            if latest.is_step_change or latest.epoch != self._epoch:
                                break
                            # Don't skip feed entries during drain
                            if latest.details.get("feed_text"):
                                self._schedule_send(latest)
                    except queue.Empty:
                        pass

                    # If we pulled a step change or stale item, handle it next iteration
                    if latest.is_step_change or latest.epoch != self._epoch:
                        self._input_queue.put(latest)
                        continue

                    remaining = self._min_interval - elapsed
                    if remaining > 0:
                        time.sleep(remaining)
                    item = latest

                self._schedule_send(item)
                self._last_send_time = time.monotonic()

            except Exception:
                logger.exception("Error in progress drain loop")

    def _schedule_send(self, item: ProgressItem):
        """Push a processed item to the main-loop send queue."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._send_queue.put_nowait, item)

    # ------------------------------------------------------------------
    # Sender task -- minimal work on the main event loop, FIFO ordering
    # ------------------------------------------------------------------

    async def _sender_loop(self):
        """Runs on the main event loop. Sends items in strict FIFO order."""
        while True:
            try:
                item = await self._send_queue.get()

                if item is None:
                    break  # Shutdown signal

                if item.epoch != self._epoch:
                    continue

                if item.is_step_change:
                    await self._broadcast_step_change(item.step)

                await self._broadcast_progress(
                    item.step, item.percent, item.message, item.details
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error in progress sender loop")
