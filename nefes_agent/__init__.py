"""nefes-agent — oturum ajanı: nefesd'nin D-Bus sinyallerini Türkçe bildirime çevirir.

Sözleşme: nefesd/tr.edu.bil461.Nefes1.xml (ADR-0003). Ajan bu dosyayı yükler; tip/alan kopyalamaz.
  AppFrozen(cgroup, app_name, memory_bytes) → "Firefox duraklatıldı … [Devam ettir]"
  AppResumed(cgroup, reason)                → o uygulamanın bildirimi kapanır
  [Devam ettir]                             → Resume(cgroup); dönüş ne olursa olsun bildirim kapanır
  nefesd göründüğünde ListFrozen ile eşitlenir; kaybolunca tüm bildirimler kapanır.

Bu modül saf mantıktır: bildirim gösterme (`notifier`) ve D-Bus çağrısı (`resume`) dışarıdan
verilir. Gerçek Gio + libnotify bağlantısı nefes_agent/__main__.py içindedir.
"""
from __future__ import annotations

import html
from collections.abc import Callable, Iterable
from typing import Protocol

MB = 1024 * 1024
_KNOWN_NAMES = {
    "firefox-esr": "Firefox", "firefox": "Firefox", "libreoffice": "LibreOffice",
    "gimp": "GIMP", "chromium": "Chromium", "thunderbird": "Thunderbird",
}


class Notifier(Protocol):
    def show(self, key: str, summary: str, body: str, on_resume: Callable[[], None]) -> None: ...
    def close(self, key: str) -> None: ...


ResumeCall = Callable[[str, Callable[[bool], None]], None]


def display_name(app_name: str) -> str:
    """Kullanıcıya gösterilecek ad: bilinen uygulamalar için tanıdık ad, diğerleri baş harfi büyük."""
    if app_name in _KNOWN_NAMES:
        return _KNOWN_NAMES[app_name]
    return (app_name[:1].upper() + app_name[1:]) or "Uygulama"


def frozen_message(app_name: str, memory_bytes: int) -> tuple[str, str]:
    """(başlık, gövde). Gövde bildirim sunucusunda markup olarak yorumlanabilir → ad kaçırılır."""
    name = display_name(app_name)
    body = f"{html.escape(name, quote=False)}, sistemin donmaması için geçici olarak duraklatıldı."
    if memory_bytes >= MB:
        body += f" {memory_bytes // MB} MB bellek boşaltılıyor."
    return f"{name} duraklatıldı", body


class Agent:
    def __init__(self, notifier: Notifier, resume: ResumeCall) -> None:
        self._notifier = notifier
        self._resume = resume
        self._open: set[str] = set()
        self._pending: set[str] = set()

    def on_frozen(self, cgroup: str, app_name: str, memory_bytes: int) -> None:
        summary, body = frozen_message(app_name, memory_bytes)
        self._notifier.show(cgroup, summary, body, lambda: self._clicked(cgroup))
        self._open.add(cgroup)

    def on_resumed(self, cgroup: str, reason: str) -> None:
        self._close(cgroup)

    def sync(self, apps: Iterable[tuple[str, str, int]]) -> None:
        """ListFrozen sonucuyla eşitle: donuk olanları göster, artık donuk olmayanları kapat."""
        frozen = {cgroup: name for cgroup, name, _seconds in apps}
        for cgroup in list(self._open):
            if cgroup not in frozen:
                self._close(cgroup)
        for cgroup, name in frozen.items():
            if cgroup not in self._open:
                self.on_frozen(cgroup, name, 0)

    def on_service_vanished(self) -> None:
        """nefesd kayboldu (çöktü/durdu): açılışta her şeyi çözer → hiçbir bildirim geçerli değil."""
        for cgroup in list(self._open):
            self._close(cgroup)
        self._pending.clear()

    def _clicked(self, cgroup: str) -> None:
        if cgroup in self._pending:
            return
        self._pending.add(cgroup)
        self._resume(cgroup, lambda ok: self._resume_done(cgroup, ok))

    def _resume_done(self, cgroup: str, _resumed: bool) -> None:
        # true: çözüldü; false: nefesd onu artık dondurmuyor → bildirim her iki durumda da bayat.
        self._pending.discard(cgroup)
        self._close(cgroup)

    def _close(self, cgroup: str) -> None:
        if cgroup in self._open:
            self._open.discard(cgroup)
            self._notifier.close(cgroup)
