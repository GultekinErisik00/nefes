"""Son olayların halkası — D-Bus RecentEvents (arayüz tasarımı, 2026-11-25).

Yalnızca bellekte, son `maxlen` olay; nefesd yeniden başlayınca boşalır (oturumlar arası geçmiş
hedef dışı). `record` notify dinleyicisi olarak D-Bus iş parçacığıyla eşzamanlı çağrılabilir:
deque.append ve tuple(deque) CPython'da tek adımdır.
"""
from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

from nefesd.eylem import Event


class EventLog:
    def __init__(self, clock: Callable[[], float] = time.time, maxlen: int = 20) -> None:
        self._clock = clock
        self._items: deque[tuple[int, str, str, str]] = deque(maxlen=maxlen)

    def record(self, event: Event, app_name: str) -> None:
        self._items.append((int(self._clock()), event.kind, app_name, event.reason))

    def items(self) -> tuple[tuple[int, str, str, str], ...]:
        return tuple(self._items)
