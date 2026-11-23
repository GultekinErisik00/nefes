"""nefesd D-Bus servisi — sözleşme: tr.edu.bil461.Nefes1.xml (tek yetkili kaynak, ADR-0003).

Oturum veriyolunda `tr.edu.bil461.Nefes1` adını alır, `/tr/edu/bil461/Nefes1` nesnesini XML'deki
arayüzle kaydeder. Yöntemler (Resume, ListFrozen) denetleyiciye (Daemon) iletilir; olaylar
(Event) sinyal olarak yayınlanır. Arayüz şekli burada tanımlanmaz: XML'den yüklenir.

İş parçacıkları: servis kendi GLib ana bağlamıyla ayrı bir iş parçacığında çalışır (`start`).
Sinyal yayınlamak (GDBusConnection.emit_signal) her iş parçacığından güvenlidir. Denetleyici
çağrıları ana döngüyle eşzamanlı olabileceğinden çağıran taraf kilitle korumalıdır (__main__).
"""
from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from nefesd.eylem import Event  # noqa: E402

log = logging.getLogger(__name__)

BUS_NAME = "tr.edu.bil461.Nefes1"
OBJECT_PATH = "/tr/edu/bil461/Nefes1"
INTERFACE = "tr.edu.bil461.Nefes1.Manager"
CONTRACT = Path(__file__).with_name("tr.edu.bil461.Nefes1.xml")

# app-[başlatıcı-]<ad>-<pid ya da 8 haneli onaltılık>.scope
_LAUNCHER_PREFIXES = ("nefes-", "gnome-", "xfce-")
_INSTANCE_SUFFIX = re.compile(r"-(?:\d+|[0-9a-f]{8})$")


class Controller(Protocol):
    def resume(self, path: str) -> bool: ...
    def frozen_durations(self) -> tuple[tuple[str, float], ...]: ...


def app_name(cgroup: str) -> str:
    """Scope yolundan kullanıcıya gösterilecek kısa ad; asla boş dönmez."""
    unit = cgroup.rstrip("/").rsplit("/", 1)[-1].removesuffix(".scope")
    name = unit.removeprefix("app-")
    for prefix in _LAUNCHER_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    name = _INSTANCE_SUFFIX.sub("", name)
    return name or unit


def signal_for(event: Event) -> tuple[str, GLib.Variant]:
    """Olayı sözleşmedeki sinyale çevirir: (sinyal adı, argümanlar)."""
    if event.kind == "frozen":
        return "AppFrozen", GLib.Variant("(sst)", (event.path, app_name(event.path), event.memory_bytes))
    return "AppResumed", GLib.Variant("(ss)", (event.path, event.reason))


class NefesService:
    METHODS = ("Resume", "ListFrozen")

    def __init__(self, controller: Controller) -> None:
        self._controller = controller
        self._connection: Gio.DBusConnection | None = None
        self._interface = Gio.DBusNodeInfo.new_for_xml(CONTRACT.read_text()).lookup_interface(INTERFACE)

    def call(self, method: str, args: tuple) -> GLib.Variant:
        """Yöntemi çalıştırır, sözleşmedeki dönüş tipinde GLib.Variant döndürür."""
        if method == "Resume":
            (path,) = args
            return GLib.Variant("(b)", (bool(self._controller.resume(path)),))
        if method == "ListFrozen":
            apps = [(path, app_name(path), int(seconds))
                    for path, seconds in self._controller.frozen_durations()]
            return GLib.Variant("(a(ssu))", (apps,))
        raise ValueError(f"bilinmeyen yöntem: {method}")

    def export(self, connection: Gio.DBusConnection) -> int:
        """Nesneyi bu bağlantıya kaydeder; çağrılar, kaydı yapan iş parçacığının bağlamında işlenir."""
        self._connection = connection
        # GLib ≥ 2.84: closures2 invocation referansını doğru yönetir; eskilerde register_object.
        register = getattr(connection, "register_object_with_closures2", connection.register_object)
        return register(OBJECT_PATH, self._interface, self._on_call, None, None)

    def emit(self, event: Event) -> None:
        if self._connection is None:
            return
        name, args = signal_for(event)
        try:
            self._connection.emit_signal(None, OBJECT_PATH, INTERFACE, name, args)
        except GLib.Error as exc:
            log.warning("D-Bus sinyali gönderilemedi (%s): %s", name, exc.message)

    def _on_call(self, _conn, _sender, _path, _iface, method, params, invocation) -> None:
        try:
            invocation.return_value(self.call(method, params.unpack()))
        except Exception as exc:  # çağıranı askıda bırakma; hatayı D-Bus hatası olarak döndür
            log.exception("D-Bus yöntemi başarısız: %s", method)
            invocation.return_dbus_error(f"{BUS_NAME}.Error.Failed", str(exc))


def start(service: NefesService, bus_type: Gio.BusType = Gio.BusType.SESSION) -> Callable[[], None]:
    """Servisi ayrı bir iş parçacığında kendi GLib döngüsüyle başlatır; durdurma işlevi döndürür."""
    ready = threading.Event()
    state: dict[str, GLib.MainLoop] = {}

    def run() -> None:
        context = GLib.MainContext.new()
        context.push_thread_default()
        loop = GLib.MainLoop.new(context, False)
        state["loop"] = loop
        owner = Gio.bus_own_name(
            bus_type, BUS_NAME, Gio.BusNameOwnerFlags.NONE,
            lambda conn, _name: service.export(conn),
            lambda _conn, name: log.info("D-Bus adı alındı: %s", name),
            lambda _conn, name: log.error("D-Bus adı alınamadı ya da kaybedildi: %s", name),
        )
        ready.set()
        try:
            loop.run()
        finally:
            Gio.bus_unown_name(owner)
            context.pop_thread_default()

    thread = threading.Thread(target=run, name="nefes-dbus", daemon=True)
    thread.start()
    ready.wait(5)

    def stop() -> None:
        loop = state.get("loop")
        if loop is not None:
            loop.quit()
        thread.join(timeout=2)

    return stop
