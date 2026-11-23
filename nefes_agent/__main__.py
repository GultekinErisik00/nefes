"""python3 -m nefes_agent — oturum ajanı (Gio D-Bus + libnotify bağlantısı).

Sözleşmeyi yalnızca XML dosyasından alır (importlib.resources ile nefesd paketinden): nefesd'nin
kodunu içe aktarmaz. Gio.DBusProxy bu arayüz bilgisiyle kurulduğundan imzası sözleşmeye uymayan
sinyaller Gio tarafından elenir.
"""
from __future__ import annotations

import logging
import signal
import sys
from importlib.resources import files

import gi

gi.require_version("Gio", "2.0")
gi.require_version("Notify", "0.7")
from gi.repository import Gio, GLib, Notify  # noqa: E402

from nefes_agent import Agent  # noqa: E402

log = logging.getLogger("nefes-agent")
BUS_NAME = "tr.edu.bil461.Nefes1"
OBJECT_PATH = "/tr/edu/bil461/Nefes1"
INTERFACE = "tr.edu.bil461.Nefes1.Manager"
CALL_TIMEOUT_MS = 5000


def contract_interface() -> Gio.DBusInterfaceInfo:
    xml = (files("nefesd") / "tr.edu.bil461.Nefes1.xml").read_text(encoding="utf-8")
    return Gio.DBusNodeInfo.new_for_xml(xml).lookup_interface(INTERFACE)


class LibnotifyNotifier:
    """Agent'ın Notifier'ı: her cgroup için tek, kalıcı, "Devam ettir" düğmeli bildirim."""

    def __init__(self) -> None:
        self._notes: dict[str, Notify.Notification] = {}

    def show(self, key, summary, body, on_resume) -> None:
        note = self._notes.get(key)
        if note is None:
            note = Notify.Notification.new(summary, body, "dialog-information")
            note.set_timeout(Notify.EXPIRES_NEVER)
            note.set_hint("desktop-entry", GLib.Variant("s", "nefes-agent"))
            note.add_action("resume", "Devam ettir", lambda *_: on_resume())
            note.connect("closed", lambda _n: self._notes.pop(key, None))
            self._notes[key] = note  # referans tutulmalı, yoksa düğme geri çağrısı kaybolur
        else:
            note.update(summary, body, "dialog-information")
        try:
            note.show()
        except GLib.Error as exc:
            log.warning("bildirim gösterilemedi: %s", exc.message)

    def close(self, key) -> None:
        note = self._notes.pop(key, None)
        if note is not None:
            try:
                note.close()
            except GLib.Error:
                pass  # kullanıcı zaten kapatmış


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not Notify.init("Nefes"):
        log.error("bildirim sistemi başlatılamadı")
        return 1
    proxy = Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SESSION,
        Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES | Gio.DBusProxyFlags.DO_NOT_AUTO_START,
        contract_interface(), BUS_NAME, OBJECT_PATH, INTERFACE, None,
    )

    def resume(cgroup, done) -> None:
        def finished(px, result):
            try:
                (resumed,) = px.call_finish(result).unpack()
            except GLib.Error as exc:
                log.warning("Resume başarısız: %s", exc.message)
                resumed = False
            done(resumed)

        proxy.call("Resume", GLib.Variant("(s)", (cgroup,)), Gio.DBusCallFlags.NONE,
                   CALL_TIMEOUT_MS, None, finished)

    agent = Agent(LibnotifyNotifier(), resume)

    def on_signal(_proxy, _sender, name, params) -> None:
        if name == "AppFrozen":
            agent.on_frozen(*params.unpack())
        elif name == "AppResumed":
            agent.on_resumed(*params.unpack())

    proxy.connect("g-signal", on_signal)

    def appeared(_conn, _name, _owner) -> None:
        log.info("nefesd göründü; donuk uygulamalar eşitleniyor")

        def listed(px, result):
            try:
                (apps,) = px.call_finish(result).unpack()
            except GLib.Error as exc:
                log.warning("ListFrozen başarısız: %s", exc.message)
                return
            agent.sync(apps)

        proxy.call("ListFrozen", None, Gio.DBusCallFlags.NONE, CALL_TIMEOUT_MS, None, listed)

    def vanished(_conn, _name) -> None:
        log.info("nefesd yok; bildirimler kapatılıyor")
        agent.on_service_vanished()

    watch = Gio.bus_watch_name(Gio.BusType.SESSION, BUS_NAME, Gio.BusNameWatcherFlags.NONE,
                               appeared, vanished)
    loop = GLib.MainLoop()

    def stop() -> bool:
        agent.on_service_vanished()
        loop.quit()
        return GLib.SOURCE_REMOVE

    GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGTERM, stop)
    GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGINT, stop)
    log.info("nefes-agent başladı")
    loop.run()
    Gio.bus_unwatch_name(watch)
    Notify.uninit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
