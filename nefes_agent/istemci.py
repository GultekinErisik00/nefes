"""nefesd istemcisi — durum modeli (saf) ve Gio D-Bus bağlantısı (arayüz tasarımı, 2026-11-25).

`Model` simgenin ve pencerenin gösterdiği durumu tutar; GTK/Gio'ya dokunmaz, test edilir.
`NefesClient` sözleşmeyi yalnızca XML'den yükler (nefesd kodunu içe aktarmaz, ADR-0003) ve
sinyalleri dinleyicilere iletir. Tüm çağrılar asenkrondur: GTK ana döngüsü bloklanmaz.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from importlib.resources import files

log = logging.getLogger("nefes-agent")
BUS_NAME = "tr.edu.bil461.Nefes1"
OBJECT_PATH = "/tr/edu/bil461/Nefes1"
INTERFACE = "tr.edu.bil461.Nefes1.Manager"
CALL_TIMEOUT_MS = 5000


class Model:
    def __init__(self) -> None:
        self.service_up = False
        self.enabled = True
        self.level = "safe"
        self._frozen: dict[str, tuple[str, int, float]] = {}  # cgroup → (ad, bayt, donma anı)
        self._listeners: list[Callable[[], None]] = []

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def on_appeared(self) -> None:
        self.service_up = True
        self._changed()

    def on_vanished(self) -> None:
        self.service_up = False
        self._frozen.clear()  # nefesd açılışta/kapanışta her şeyi çözer
        self._changed()

    def on_status(self, enabled: bool, level: str) -> None:
        self.enabled, self.level = enabled, level
        self._changed()

    def on_frozen(self, cgroup: str, name: str, nbytes: int, now: float) -> None:
        self._frozen[cgroup] = (name, nbytes, now)
        self._changed()

    def on_resumed(self, cgroup: str) -> None:
        self._frozen.pop(cgroup, None)
        self._changed()

    def sync(self, apps: Iterable[tuple[str, str, int]], now: float) -> None:
        """ListFrozen sonucu: (cgroup, ad, kaç saniyedir donuk). Bilinen boyutlar korunur."""
        self._frozen = {
            cgroup: (name, self._frozen.get(cgroup, (name, 0, 0.0))[1], now - seconds)
            for cgroup, name, seconds in apps
        }
        self._changed()

    def frozen_rows(self, now: float) -> list[tuple[str, str, int, int]]:
        """(cgroup, ad, bayt, geçen saniye) — en eski önce."""
        rows = sorted(self._frozen.items(), key=lambda item: item[1][2])
        return [(cgroup, name, nbytes, int(now - since)) for cgroup, (name, nbytes, since) in rows]

    def _changed(self) -> None:
        for listener in self._listeners:
            listener()


def contract_interface():
    from gi.repository import Gio
    xml = (files("nefesd") / "tr.edu.bil461.Nefes1.xml").read_text(encoding="utf-8")
    return Gio.DBusNodeInfo.new_for_xml(xml).lookup_interface(INTERFACE)


class NefesClient:
    """Tek Gio.DBusProxy üzerinde asenkron çağrılar + sinyal/ad izleme."""

    def __init__(self) -> None:
        from gi.repository import Gio
        self._proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION,
            Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES | Gio.DBusProxyFlags.DO_NOT_AUTO_START,
            contract_interface(), BUS_NAME, OBJECT_PATH, INTERFACE, None,
        )
        self.on_frozen: list[Callable[[str, str, int], None]] = []
        self.on_resumed: list[Callable[[str, str], None]] = []
        self.on_status: list[Callable[[bool, str], None]] = []
        self.on_appeared: list[Callable[[], None]] = []
        self.on_vanished: list[Callable[[], None]] = []
        self._proxy.connect("g-signal", self._signal)
        self._watch = Gio.bus_watch_name(
            Gio.BusType.SESSION, BUS_NAME, Gio.BusNameWatcherFlags.NONE,
            lambda *_: self._fire(self.on_appeared), lambda *_: self._fire(self.on_vanished))

    def close(self) -> None:
        from gi.repository import Gio
        Gio.bus_unwatch_name(self._watch)

    # --- yöntemler (done(sonuç) ya da hata durumunda done(None)) -------------------------
    def resume(self, cgroup: str, done: Callable[[bool], None]) -> None:
        from gi.repository import GLib
        self._call("Resume", GLib.Variant("(s)", (cgroup,)), lambda r: done(bool(r and r[0])))

    def list_frozen(self, done: Callable[[list | None], None]) -> None:
        self._call("ListFrozen", None, lambda r: done(None if r is None else list(r[0])))

    def get_status(self, done: Callable[[tuple | None], None]) -> None:
        self._call("GetStatus", None, done)

    def set_enabled(self, enabled: bool, done: Callable[[object], None] = lambda _r: None) -> None:
        from gi.repository import GLib
        self._call("SetEnabled", GLib.Variant("(b)", (enabled,)), done)

    def reload_settings(self, done: Callable[[tuple | None], None]) -> None:
        self._call("ReloadSettings", None, done)

    def recent_events(self, done: Callable[[list | None], None]) -> None:
        self._call("RecentEvents", None, lambda r: done(None if r is None else list(r[0])))

    # --- iç ------------------------------------------------------------------------------
    def _call(self, method: str, args, done: Callable[[tuple | None], None]) -> None:
        from gi.repository import Gio, GLib

        def finished(proxy, result):
            try:
                value = proxy.call_finish(result).unpack()
            except GLib.Error as exc:
                log.warning("%s başarısız: %s", method, exc.message)
                value = None
            done(value)

        self._proxy.call(method, args, Gio.DBusCallFlags.NONE, CALL_TIMEOUT_MS, None, finished)

    def _signal(self, _proxy, _sender, name, params) -> None:
        args = params.unpack()
        if name == "AppFrozen":
            for listener in self.on_frozen:
                listener(*args)
        elif name == "AppResumed":
            for listener in self.on_resumed:
                listener(*args)
        elif name == "StatusChanged":
            for listener in self.on_status:
                listener(*args)

    @staticmethod
    def _fire(listeners: list[Callable[[], None]]) -> None:
        for listener in listeners:
            listener()
