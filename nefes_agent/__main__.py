"""python3 -m nefes_agent [--pencere] — oturum ajanı: bildirimler + panel simgesi + pencere (ADR-0004).

Tek örnekli Gtk.Application: menüden `nefes-agent --pencere` çalışan ajana iletilir ve penceresini
öne getirir; ajan yoksa bu süreç ajan olur. Sözleşmeyi yalnızca XML dosyasından alır
(nefes_agent.istemci): nefesd'nin kodunu içe aktarmaz.
"""
from __future__ import annotations

import logging
import signal
import sys
import time

import gi

gi.require_version("Gio", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Notify", "0.7")
from gi.repository import Gio, GLib, Gtk, Notify  # noqa: E402

import nefes_ayar  # noqa: E402
from nefes_agent import Agent  # noqa: E402
from nefes_agent.istemci import Model, NefesClient  # noqa: E402

log = logging.getLogger("nefes-agent")
APP_ID = "tr.edu.bil461.NefesAgent"


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


class NefesApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self._window = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        if not Notify.init("Nefes"):
            log.error("bildirim sistemi başlatılamadı; yalnızca simge ve pencere çalışacak")
        self.settings_path = nefes_ayar.config_path()
        self.model = Model()
        self.client = NefesClient()
        self.agent = Agent(LibnotifyNotifier(), self.client.resume,
                           notifications_enabled=lambda: nefes_ayar.load(self.settings_path)[0].notifications)
        self._wire()
        from nefes_agent.simge import Tray
        self.tray = Tray.create(self.model, self.client, self.show_window, self.set_enabled)
        GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGTERM, self._stop)
        GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGINT, self._stop)
        self.hold()  # pencere yokken de yaşa
        log.info("nefes-agent başladı (simge: %s)", "var" if self.tray else "yok")

    def do_command_line(self, command_line) -> int:
        if "--pencere" in command_line.get_arguments()[1:]:
            self.show_window()
        return 0

    def do_activate(self) -> None:
        self.show_window()

    def show_window(self) -> None:
        if self._window is None:
            from nefes_agent.pencere import Window
            self._window = Window(self, self.model, self.client, self.settings_path, self.set_enabled)
        self._window.present()

    def set_enabled(self, enabled: bool) -> None:
        """Duraklat/sürdür: önce dosyaya (kalıcı, tek yazar ajan), sonra nefesd'ye (anında)."""
        try:
            nefes_ayar.update(self.settings_path, enabled=enabled)
        except OSError as exc:
            log.warning("ayar dosyası yazılamadı: %s", exc)
        self.client.set_enabled(enabled)

    def _wire(self) -> None:
        client, model, agent = self.client, self.model, self.agent

        def frozen(cgroup, name, nbytes) -> None:
            model.on_frozen(cgroup, name, nbytes, time.monotonic())
            agent.on_frozen(cgroup, name, nbytes)

        def resumed(cgroup, reason) -> None:
            model.on_resumed(cgroup)
            agent.on_resumed(cgroup, reason)

        def appeared() -> None:
            log.info("nefesd göründü; durum eşitleniyor")
            model.on_appeared()
            client.list_frozen(lambda apps: apps is not None and (
                model.sync(apps, time.monotonic()), agent.sync(apps)))
            client.get_status(lambda st: st is not None and model.on_status(st[0], st[1]))

        def vanished() -> None:
            log.info("nefesd yok; bildirimler kapatılıyor")
            model.on_vanished()
            agent.on_service_vanished()

        client.on_frozen.append(frozen)
        client.on_resumed.append(resumed)
        client.on_status.append(model.on_status)
        client.on_appeared.append(appeared)
        client.on_vanished.append(vanished)

    def _stop(self) -> bool:
        self.agent.on_service_vanished()
        self.client.close()
        Notify.uninit()
        self.quit()
        return GLib.SOURCE_REMOVE


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return NefesApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
