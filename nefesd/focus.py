"""X11 odak bilgisi: _NET_ACTIVE_WINDOW → _NET_WM_PID → cgroup yolu (ADR-0002).

Dönüş: (odaktaki cgroup yolu | None, odak_biliniyor_mu). Odak okunamazsa (X yok, pencere
PID bildirmiyor, süreç bitti) biliniyor=False döner; karar motoru o turda hiçbir şeyi dondurmaz.
"""
from __future__ import annotations

import logging
from pathlib import Path

from nefesd.cgroups import cgroup_of_pid

log = logging.getLogger(__name__)


class X11Focus:
    def __init__(self, proc_root: Path = Path("/proc")) -> None:
        self._proc_root = proc_root
        self._display = None

    def __call__(self) -> tuple[str | None, bool]:
        try:
            return self._read()
        except Exception as exc:  # X bağlantısı koptu vb. — güvenli taraf: bilinmiyor
            log.warning("odak okunamadı: %s", exc)
            self._close()
            return None, False

    def _close(self) -> None:
        if self._display is not None:
            try:
                self._display.close()
            except Exception:
                pass
            self._display = None

    def _read(self) -> tuple[str | None, bool]:
        from Xlib import X, display  # python3-xlib; yalnızca X oturumunda gerekli

        if self._display is None:
            self._display = display.Display()
        d = self._display
        active = d.screen().root.get_full_property(d.intern_atom("_NET_ACTIVE_WINDOW"), X.AnyPropertyType)
        if active is None or not active.value or active.value[0] == 0:
            return None, False  # pencere geçişi sırasında olabilir → bilinmiyor (güvenli taraf)
        window = d.create_resource_object("window", active.value[0])
        pid = window.get_full_property(d.intern_atom("_NET_WM_PID"), X.AnyPropertyType)
        if pid is None or not pid.value:
            return None, False  # pencere PID bildirmiyor → bilinmiyor
        path = cgroup_of_pid(int(pid.value[0]), self._proc_root)
        return (path, True) if path is not None else (None, False)
