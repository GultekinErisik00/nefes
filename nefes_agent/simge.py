"""Panel simgesi — Ayatana AppIndicator (ADR-0004). Kütüphane yoksa simge atlanır.

Durum ve metinler gorunum.tray_state'ten gelir; menü her model değişikliğinde yeniden kurulur.
Simge yalnızca sinyallerle güncellenir (yoklama yok).
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from nefes_agent import display_name  # noqa: E402
from nefes_agent.gorunum import format_duration, tray_state  # noqa: E402
from nefes_agent.istemci import Model, NefesClient  # noqa: E402

log = logging.getLogger("nefes-agent")
SYSTEM_ICON = Path("/usr/share/icons/hicolor/scalable/status/nefes-normal.svg")
REPO_ICONS = Path(__file__).resolve().parent.parent / "data" / "icons"


def _indicator_module():
    try:
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3
    except (ValueError, ImportError) as exc:
        log.warning("panel simgesi yok (AyatanaAppIndicator3 bulunamadı): %s", exc)
        return None
    return AyatanaAppIndicator3


class Tray:
    def __init__(self, indicator_module, model: Model, client: NefesClient,
                 show_window: Callable[[], None], set_enabled: Callable[[bool], None]) -> None:
        self._ai, self._model, self._client = indicator_module, model, client
        self._show_window, self._set_enabled = show_window, set_enabled
        self._indicator = self._ai.Indicator.new(
            "nefes", "nefes-normal", self._ai.IndicatorCategory.APPLICATION_STATUS)
        if not SYSTEM_ICON.exists() and REPO_ICONS.is_dir():  # paket kurulmadan geliştirme
            self._indicator.set_icon_theme_path(str(REPO_ICONS))
        self._indicator.set_title("Nefes")
        self._indicator.set_status(self._ai.IndicatorStatus.ACTIVE)
        model.subscribe(self.refresh)
        self.refresh()

    @classmethod
    def create(cls, model: Model, client: NefesClient, show_window: Callable[[], None],
               set_enabled: Callable[[bool], None]) -> "Tray | None":
        module = _indicator_module()
        return None if module is None else cls(module, model, client, show_window, set_enabled)

    def refresh(self) -> None:
        rows = self._model.frozen_rows(time.monotonic())
        icon, tooltip = tray_state(self._model.service_up, self._model.enabled, self._model.level, len(rows))
        self._indicator.set_icon_full(icon, tooltip)
        self._indicator.set_menu(self._menu(tooltip, rows))

    def _menu(self, tooltip: str, rows) -> Gtk.Menu:
        menu = Gtk.Menu()
        header = Gtk.MenuItem(label=tooltip)
        header.set_sensitive(False)
        menu.append(header)
        if rows:
            menu.append(Gtk.SeparatorMenuItem())
            for cgroup, name, _nbytes, seconds in rows:
                item = Gtk.MenuItem(label=f"{display_name(name)} ({format_duration(seconds)}) — Devam ettir")
                item.connect("activate", lambda _i, c=cgroup: self._client.resume(c, lambda _ok: None))
                menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())
        open_item = Gtk.MenuItem(label="Nefes'i aç…")
        open_item.connect("activate", lambda _i: self._show_window())
        menu.append(open_item)
        toggle = Gtk.MenuItem(label="Duraklat" if self._model.enabled else "Sürdür")
        toggle.set_sensitive(self._model.service_up)
        toggle.connect("activate", lambda _i: self._set_enabled(not self._model.enabled))
        menu.append(toggle)
        menu.show_all()
        return menu
