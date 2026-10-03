"""Fan-out of live updates to SSE subscribers, one queue per browser connection.

Everything here runs on the asyncio event loop thread.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any

log = logging.getLogger("hub.live")

QUEUE_SIZE = 256
CLOSE = "$close"  # tells the stream generator to end


class Broadcaster:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, pump_id: str) -> asyncio.Queue[tuple[str, Any]]:
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers[pump_id].add(queue)
        return queue

    def unsubscribe(self, pump_id: str, queue: asyncio.Queue) -> None:
        self._subscribers[pump_id].discard(queue)

    def send(self, pump_id: str, event: str, data: Any) -> None:
        for queue in list(self._subscribers[pump_id]):
            try:
                queue.put_nowait((event, data))
            except asyncio.QueueFull:
                # A stuck browser. Drop it; EventSource reconnects and gets a fresh snapshot.
                log.warning("dropping slow SSE subscriber for %s", pump_id)
                self._subscribers[pump_id].discard(queue)
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait((CLOSE, None))
