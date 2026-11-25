"""Durum ve ayar penceresi — GTK 3 (arayüz tasarımı, 2026-11-25).

Bölümler taslaktaki sırayla: durum + Duraklat, baskı çizgisi, RAM/zram, donuk uygulamalar, son olaylar,
ayarlar. Pencere görünürken 2 s'de bir GetStatus + /proc okunur; gizliyken zamanlayıcı yoktur.
Ayar değişikliği: dosyaya yaz → ReloadSettings; reddedilirse eski ayar geri yazılır ve neden gösterilir.
Tüm etiketler düz metindir (set_text): uygulama adları markup olarak yorumlanmaz.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

import nefes_ayar  # noqa: E402
from nefes_agent import display_name  # noqa: E402
from nefes_agent.gorunum import (  # noqa: E402
    LEVEL_TEXT, app_choice, event_line, format_duration, format_mb, sparkline,
)
from nefes_agent.istemci import Model, NefesClient  # noqa: E402
from nefes_agent.sistem import read_memory  # noqa: E402
from nefes_ayar import MAX_FROZEN_CHOICES_MIN, Settings  # noqa: E402

log = logging.getLogger("nefes-agent")
REFRESH_SECONDS = 2
HISTORY = 30  # 1 dk; 60 karakterlik çizgi pencereyi ekrandan taşırıyordu (VM, 25 Kas)
SENSITIVITY_LABELS = (("az", "Az"), ("orta", "Orta"), ("cok", "Çok"))


def _section(title: str) -> Gtk.Label:
    label = Gtk.Label(xalign=0)
    label.set_markup(f"<b>{GLib.markup_escape_text(title)}</b>")
    return label


class Window(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, model: Model, client: NefesClient,
                 settings_path: Path, set_enabled: Callable[[bool], None]) -> None:
        super().__init__(application=app, title="Nefes")
        self.set_default_size(460, -1)
        self.set_icon_name("nefes-normal")
        self._model, self._client, self._path, self._set_enabled = model, client, settings_path, set_enabled
        self._history: deque[float] = deque(maxlen=HISTORY)
        self._timer: int | None = None
        self._updating = False
        self._build()
        model.subscribe(self._refresh_model)
        self.connect("delete-event", lambda *_: self.hide() or True)  # kapat = gizle; ajan sürer
        self.connect("map", lambda *_: self._start())
        self.connect("unmap", lambda *_: self._stop())
        self._load_settings()
        self._refresh_model()

    # --- yerleşim ------------------------------------------------------------------------
    def _build(self) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=14)
        self.add(box)
        self._info = Gtk.InfoBar(message_type=Gtk.MessageType.WARNING, show_close_button=True)
        self._info_label = Gtk.Label(xalign=0, wrap=True)
        self._info.get_content_area().add(self._info_label)
        self._info.connect("response", lambda bar, _r: bar.hide())
        self._info.set_no_show_all(True)
        box.pack_start(self._info, False, False, 0)

        head = Gtk.Box(spacing=8)
        self._state = Gtk.Label(xalign=0, hexpand=True)
        self._toggle = Gtk.Button()
        self._toggle.connect("clicked", lambda _b: self._set_enabled(not self._model.enabled))
        head.pack_start(self._state, True, True, 0)
        head.pack_end(self._toggle, False, False, 0)
        box.pack_start(head, False, False, 0)
        self._pressure = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self._memory = Gtk.Label(xalign=0)
        box.pack_start(self._pressure, False, False, 0)
        box.pack_start(self._memory, False, False, 0)

        box.pack_start(Gtk.Separator(), False, False, 0)
        box.pack_start(_section("Dondurulan uygulamalar"), False, False, 0)
        self._frozen = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        empty = Gtk.Label(label="Şu an dondurulmuş uygulama yok.", xalign=0)
        empty.show()  # GTK 3'te get_placeholder yok; yer tutucu kendi başına gösterilmeli
        self._frozen.set_placeholder(empty)
        box.pack_start(self._frozen, False, False, 0)

        box.pack_start(Gtk.Separator(), False, False, 0)
        box.pack_start(_section("Son olaylar"), False, False, 0)
        self._events = Gtk.Label(xalign=0, yalign=0)
        box.pack_start(self._events, False, False, 0)

        box.pack_start(Gtk.Separator(), False, False, 0)
        box.pack_start(_section("Ayarlar"), False, False, 0)
        grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        box.pack_start(grid, False, False, 0)

        grid.attach(Gtk.Label(label="Hassasiyet", xalign=0), 0, 0, 1, 1)
        radios, group = Gtk.Box(spacing=6), None
        self._sensitivity: dict[str, Gtk.RadioButton] = {}
        for key, text in SENSITIVITY_LABELS:
            radio = Gtk.RadioButton.new_with_label_from_widget(group, text)
            group = group or radio
            radio.connect("toggled", self._on_sensitivity, key)
            self._sensitivity[key] = radio
            radios.pack_start(radio, False, False, 0)
        grid.attach(radios, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="En uzun donma", xalign=0), 0, 1, 1, 1)
        self._max_frozen = Gtk.ComboBoxText()
        for minutes in MAX_FROZEN_CHOICES_MIN:
            self._max_frozen.append(str(minutes), f"{minutes} dk")
        self._max_frozen.connect("changed", self._on_max_frozen)
        grid.attach(self._max_frozen, 1, 1, 1, 1)

        grid.attach(Gtk.Label(label="Asla dondurma", xalign=0, yalign=0), 0, 2, 1, 1)
        never = Gtk.Box(spacing=6)
        self._never = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4)
        add = Gtk.Button(label="+ Ekle")
        add.connect("clicked", lambda _b: self._choose_app())
        never.pack_start(self._never, True, True, 0)
        never.pack_end(add, False, False, 0)
        grid.attach(never, 1, 2, 1, 1)

        grid.attach(Gtk.Label(label="Bildirim göster", xalign=0), 0, 3, 1, 1)
        self._notify = Gtk.CheckButton()
        self._notify.connect("toggled", self._on_notify)
        grid.attach(self._notify, 1, 3, 1, 1)
        box.show_all()

    # --- durum ---------------------------------------------------------------------------
    def _refresh_model(self) -> None:
        model = self._model
        if not model.service_up:
            self._state.set_text("● Nefes çalışmıyor")
        else:
            self._state.set_text("● Nefes açık" if model.enabled else "● Nefes duraklatıldı")
        self._toggle.set_label("Duraklat" if model.enabled else "Sürdür")
        self._toggle.set_sensitive(model.service_up)
        for child in self._frozen.get_children():
            self._frozen.remove(child)
        for cgroup, name, nbytes, seconds in model.frozen_rows(time.monotonic()):
            row = Gtk.Box(spacing=10, margin=2)
            parts = [display_name(name), format_duration(seconds)]
            if nbytes:
                parts.insert(1, format_mb(nbytes))
            row.pack_start(Gtk.Label(label="   ".join(parts), xalign=0), True, True, 0)
            button = Gtk.Button(label="Devam ettir")
            button.set_sensitive(model.service_up)
            button.connect("clicked", lambda _b, c=cgroup: self._client.resume(c, lambda _ok: None))
            row.pack_end(button, False, False, 0)
            self._frozen.add(row)
        self._frozen.show_all()
        self._draw_pressure()

    def _draw_pressure(self) -> None:
        level = LEVEL_TEXT.get(self._model.level, self._model.level) if self._model.service_up else "—"
        self._pressure.set_text(f"Bellek baskısı  {sparkline(self._history, HISTORY) or '▁'}  {level}")

    def _start(self) -> None:
        if self._timer is None:
            self._tick()
            self._timer = GLib.timeout_add_seconds(REFRESH_SECONDS, self._tick)

    def _stop(self) -> None:
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def _tick(self) -> bool:
        if self._model.service_up:
            self._client.get_status(self._got_status)
            self._client.recent_events(self._got_events)
        self._refresh_memory()
        self._refresh_model()  # geçen süreler güncellensin
        return GLib.SOURCE_CONTINUE

    def _got_status(self, status) -> None:
        if status is None:
            return
        enabled, level, avg10 = status
        self._history.append(avg10)
        if (enabled, level) != (self._model.enabled, self._model.level):
            self._model.on_status(enabled, level)
        else:
            self._draw_pressure()

    def _got_events(self, events) -> None:
        if events is None:
            return
        lines = [event_line(*item) for item in reversed(events[-6:])]
        self._events.set_text("\n".join(lines) or "Henüz olay yok.")

    def _refresh_memory(self) -> None:
        try:
            (used, total), zram = read_memory()
        except OSError as exc:
            self._memory.set_text(f"Bellek okunamadı: {exc}")
            return
        text = f"RAM {format_mb(used)} / {format_mb(total)}"
        if zram is not None:
            text += f"   ·   zram {format_mb(zram[0])} → {format_mb(zram[1])}"
        self._memory.set_text(text)

    # --- ayarlar -------------------------------------------------------------------------
    def _load_settings(self) -> None:
        settings, warnings = nefes_ayar.load(self._path)
        if warnings:
            self._show_info("Ayar dosyasında sorun: " + "; ".join(warnings))
        self._settings = settings
        self._updating = True
        try:
            self._sensitivity[settings.sensitivity].set_active(True)
            self._max_frozen.set_active_id(str(settings.max_frozen_min))
            self._notify.set_active(settings.notifications)
            self._draw_never()
        finally:
            self._updating = False

    def _apply(self, **changes) -> None:
        if self._updating:
            return
        try:
            old, new = nefes_ayar.update(self._path, **changes)
        except OSError as exc:
            self._show_info(f"Ayarlar kaydedilemedi: {exc}")
            self._load_settings()
            return
        self._settings = new
        if new == old:
            return
        self._draw_never()

        def done(result) -> None:
            if result is None:
                return  # nefesd yok: dosya yazıldı, açılışta okunur
            ok, message = result
            if not ok:
                try:
                    nefes_ayar.save(self._path, old)
                except OSError as exc:
                    log.warning("eski ayar geri yazılamadı: %s", exc)
                self._show_info(f"Ayar uygulanmadı: {message}")
                self._load_settings()

        self._client.reload_settings(done)

    def _on_sensitivity(self, radio: Gtk.RadioButton, key: str) -> None:
        if radio.get_active():
            self._apply(sensitivity=key)

    def _on_max_frozen(self, combo: Gtk.ComboBoxText) -> None:
        if combo.get_active_id():
            self._apply(max_frozen_min=int(combo.get_active_id()))

    def _on_notify(self, check: Gtk.CheckButton) -> None:
        self._apply(notifications=check.get_active())

    def _draw_never(self) -> None:
        for child in self._never.get_children():
            self._never.remove(child)
        for name in self._settings.never_freeze:
            button = Gtk.Button(label=f"{name} ✕")
            button.set_tooltip_text("Listeden çıkar")
            button.connect("clicked", lambda _b, n=name: self._apply(
                never_freeze=tuple(x for x in self._settings.never_freeze if x != n)))
            self._never.add(button)
        self._never.show_all()

    def _choose_app(self) -> None:
        from nefes_baslat import SOURCE_DIRS, menu_apps

        choices: dict[str, str] = {}
        for desktop_id in menu_apps(SOURCE_DIRS):
            for directory in SOURCE_DIRS:
                path = directory / f"{desktop_id}.desktop"
                if path.is_file():
                    try:
                        choice = app_choice(path.read_text(encoding="utf-8"))
                    except (OSError, UnicodeDecodeError):
                        choice = None
                    if (choice
                            and nefes_ayar.is_valid_never_freeze(choice[1])
                            and choice[1] not in self._settings.never_freeze):
                        choices.setdefault(choice[0], choice[1])
                    break
        dialog = Gtk.Dialog(title="Asla dondurulmayacak uygulama", transient_for=self, modal=True)
        dialog.add_buttons("Vazgeç", Gtk.ResponseType.CANCEL, "Ekle", Gtk.ResponseType.OK)
        combo = Gtk.ComboBoxText()
        for label in sorted(choices, key=str.casefold):
            combo.append(choices[label], label)
        combo.set_active(0)
        dialog.get_content_area().add(combo)
        dialog.get_content_area().set_border_width(12)
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK and combo.get_active_id():
            self._apply(never_freeze=(*self._settings.never_freeze, combo.get_active_id()))
        dialog.destroy()

    def _show_info(self, text: str) -> None:
        self._info_label.set_text(text)
        self._info.show()
        self._info_label.show()
