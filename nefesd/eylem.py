"""nefesd ana döngüsünün çekirdeği — durum, eylem uygulama, zamanlayıcılar.

`Daemon` dosya sistemine, saate ve odağa doğrudan dokunmaz; hepsi dışarıdan verilir
(Ops, clock, focus, notify). Böylece döngü sahte saatle test edilir; gerçek bağlantılar
`nefesd.__main__` içindedir.

Güvenlik: yalnızca bu daemon'ın dondurduğu uygulamalar takip edilir ve çözülür; açılışta
diskte donuk kalmış her şey çözülür; kapanışta dondurulan her şey çözülür; zaman aşımıyla
çözülen uygulama `cooldown_seconds` boyunca yeniden aday olmaz (sınırsız donukluk olmasın).
`clock` monoton olmalıdır (time.monotonic).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from nefesd.cgroups import ReclaimResult, ScopeGone
from nefesd.karar import Action, AppCgroup, Freeze, Policy, Snapshot, decide
from nefesd.psi import classify

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    policy: Policy
    cooldown_seconds: float  # zaman aşımıyla/kullanıcıyla çözülen uygulama bu süre aday olmaz
    safe_below: float  # PSI some avg10 bu değerin altındaysa baskı "güvenli"
    safe_check_seconds: float  # donuk uygulama varken en geç bu aralıkla uyanıp baskıya bak


@dataclass(frozen=True)
class Event:
    kind: str  # "frozen" | "resumed"
    path: str
    reason: str  # frozen: "pressure"; resumed: "focus" | "timeout" | "pressure_low" | "user" | "shutdown"
    memory_bytes: int  # frozen: dondurma anındaki memory.current; resumed: 0 (sözleşme, ADR-0003)


def _run_now(job: Callable[[], None]) -> None:
    job()


class Ops(Protocol):
    def read_apps(self, frozen_since: dict[str, float]) -> tuple[AppCgroup, ...]: ...
    def list_frozen(self) -> tuple[str, ...]: ...
    def freeze(self, path: str) -> None: ...
    def thaw(self, path: str) -> None: ...
    def reclaim(self, path: str, nbytes: int) -> ReclaimResult: ...


class Daemon:
    def __init__(
        self,
        config: Config,
        ops: Ops,
        clock: Callable[[], float],
        focus: Callable[[], tuple[str | None, bool]],
        notify: Callable[[Event], None],
        run_async: Callable[[Callable[[], None]], None] | None = None,
        on_status: Callable[[bool, str], None] | None = None,
        enabled: bool = True,
    ) -> None:
        self._config = config
        self._ops = ops
        self._clock = clock
        self._focus = focus
        self._notify = notify
        self._run_async = run_async or _run_now
        self._frozen_since: dict[str, float] = {}
        self._cooldown_until: dict[str, float] = {}
        self._on_status = on_status or (lambda _enabled, _level: None)
        self._enabled = enabled
        self._level = "safe"  # Pressure değeri: "safe" | "normal" | "high"
        self._avg10 = 0.0

    def startup(self) -> None:
        """Önceki çalışmadan donuk kalmış scope'ları çözer (ne zamandan beri donuk bilinmez)."""
        for path in self._ops.list_frozen():
            try:
                self._ops.thaw(path)
            except ScopeGone:
                continue
            except OSError as exc:
                log.error("açılışta çözülemedi %s: %s", path, exc)

    def tick(self, fired: bool, some_avg10: float) -> tuple[Action, ...]:
        """Bir tur: durumu oku, karar ver, uygula. Uygulanmak istenen eylemleri döndürür."""
        now = self._clock()
        pressure = classify(fired, some_avg10, self._config.safe_below)
        self._avg10 = some_avg10
        if pressure.value != self._level:
            self._level = pressure.value
            self._on_status(self._enabled, self._level)
        if not self._enabled:  # duraklatıldı: karar yok; çözülemeyen kalırsa yeniden dene
            for path in list(self._frozen_since):
                self._thaw(path, "paused", now)
            return ()
        apps = self._ops.read_apps(dict(self._frozen_since))
        self._forget_missing({a.path for a in apps}, now)
        eligible = tuple(a for a in apps if not self._cooling_down(a, now))
        focus_path, focus_known = self._focus()
        snapshot = Snapshot(
            apps=eligible,
            focus_path=focus_path,
            focus_known=focus_known,
            pressure=pressure,
            now=now,
        )
        actions = decide(snapshot, self._config.policy)
        memory = {a.path: a.memory_current for a in apps}
        for action in actions:
            if isinstance(action, Freeze):
                self._freeze(action.path, memory.get(action.path, 0), now)
            else:
                self._thaw(action.path, action.reason, now)
        return actions

    def set_enabled(self, enabled: bool) -> None:
        """Duraklat/sürdür. Duraklatınca dondurulan her şey "paused" nedeniyle çözülür."""
        if enabled == self._enabled:
            return
        self._enabled = enabled
        if not enabled:
            now = self._clock()
            for path in list(self._frozen_since):
                self._thaw(path, "paused", now)
        self._on_status(self._enabled, self._level)

    def reconfigure(self, config: Config) -> None:
        """Yeni ayarlar sonraki turdan itibaren geçerli; donuk uygulamalar korunur."""
        self._config = config

    def status(self) -> tuple[bool, str, float]:
        """(etkin mi, son baskı seviyesi, son some avg10) — D-Bus GetStatus için."""
        return self._enabled, self._level, self._avg10

    def resume(self, path: str) -> bool:
        """Kullanıcının "Devam ettir" isteği; yalnızca bu daemon'ın dondurduğu uygulamalar."""
        if path not in self._frozen_since:
            return False
        return self._thaw(path, "user", self._clock())

    def shutdown(self) -> None:
        """Servis dururken dondurulan her şeyi çözer; biri başarısız olsa da diğerlerine devam eder."""
        now = self._clock()
        for path in list(self._frozen_since):
            self._thaw(path, "shutdown", now)

    def frozen_durations(self) -> tuple[tuple[str, float], ...]:
        """(yol, kaç saniyedir donuk) — dondurulma sırasına göre; D-Bus ListFrozen için."""
        now = self._clock()
        ordered = sorted(self._frozen_since.items(), key=lambda item: item[1])
        return tuple((path, now - since) for path, since in ordered)

    def frozen_paths(self) -> tuple[str, ...]:
        return tuple(sorted(self._frozen_since))

    def poll_timeout(self) -> float | None:
        """PSI beklemesi için zaman aşımı (s): donuk yoksa ve baskı güvenliyse None (sonsuz).
        Baskı güvenli değilken de uyanılır: yoksa son seviye (ör. "high") boşta hep öyle kalır
        ve StatusChanged hiç gelmez (VM'de bulundu, 2026-11-25)."""
        if not self._frozen_since:
            return None if self._level == "safe" else self._config.safe_check_seconds
        deadline = min(self._frozen_since.values()) + self._config.policy.max_frozen_seconds
        remaining = max(0.0, deadline - self._clock())
        return min(self._config.safe_check_seconds, remaining)

    # --- iç -------------------------------------------------------------------

    def _freeze(self, path: str, memory_current: int, now: float) -> None:
        # Önce kaydet, sonra dondur: arada bir sinyal gelse bile kapanışta çözülecekler listesinde.
        # Not: frozen_since, (birkaç saniye sürebilen) reclaim'den ÖNCE damgalanır.
        self._frozen_since[path] = now
        try:
            self._ops.freeze(path)
        except ScopeGone:
            self._frozen_since.pop(path, None)
            return
        except OSError as exc:
            log.error("dondurulamadı %s: %s — geri alınıyor", path, exc)
            self._frozen_since.pop(path, None)
            self._undo_freeze(path)
            return
        # Bildirim dondurma ANINDA, bu iş parçacığından: aynı uygulamanın "resumed" olayı ondan önce
        # gidemez (gerçek veriyolunda bulunan sıra hatası, 2026-11-23).
        self._notify(Event("frozen", path, "pressure", memory_current))
        # Geri kazanım saniyeler sürebilir (disk swap'ta ~6 s): ana döngüyü bloklamasın.
        if memory_current > 0:
            self._run_async(lambda: self._reclaim(path, memory_current))

    def _reclaim(self, path: str, memory_current: int) -> None:
        """Arka planda çalışır; daemon durumuna DOKUNMAZ ve olay üretmez (yalnızca günlük).
        Uygulama bu arada kapanırsa sonraki tur onu zaten takipten çıkarır."""
        try:
            result = self._ops.reclaim(path, memory_current)
        except ScopeGone:
            return
        except (OSError, ValueError) as exc:
            log.warning("geri kazanım başarısız %s: %s (uygulama donuk kalıyor)", path, exc)
            return
        log.info("geri kazanıldı %s: %d MB", path.rsplit("/", 1)[-1],
                 max(0, result.before - result.after) // (1024 * 1024))

    def _undo_freeze(self, path: str) -> None:
        try:
            self._ops.thaw(path)
        except (ScopeGone, OSError) as exc:
            log.error("yarım dondurma geri alınamadı %s: %s", path, exc)

    def _thaw(self, path: str, reason: str, now: float) -> bool:
        """Çözer; başarısız olursa (ör. EBUSY) uygulama takipte kalır ve sonraki turda yeniden denenir."""
        try:
            self._ops.thaw(path)
        except ScopeGone:
            self._frozen_since.pop(path, None)
            return False
        except OSError as exc:
            log.error("çözülemedi %s (%s): %s — sonraki turda yeniden denenecek", path, reason, exc)
            return False
        self._frozen_since.pop(path, None)
        self._cooldown_until[path] = now + self._config.cooldown_seconds
        self._notify(Event("resumed", path, reason, 0))
        return True

    def _cooling_down(self, app: AppCgroup, now: float) -> bool:
        return app.frozen_since is None and self._cooldown_until.get(app.path, 0.0) > now

    def _forget_missing(self, present: set[str], now: float) -> None:
        for path in [p for p in self._frozen_since if p not in present]:
            del self._frozen_since[path]
        for path in [p for p, until in self._cooldown_until.items() if until <= now or p not in present]:
            del self._cooldown_until[path]
