"""nefesd giriş noktası: python3 -m nefesd

PSI tetikleyicisini kurar, poll() ile bekler (baskı yokken CPU kullanmaz), her olayda ya da
zamanlayıcıda Daemon.tick() çağırır. SIGTERM/SIGINT'te dondurduğu her şeyi çözerek çıkar.
Prototip aşamasında kullanıcı olarak çalışır (cgroup delegasyonu yeterli; root gerekmez).
"""
from __future__ import annotations

import argparse
import logging
import math
import os
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
import select
import signal
import sys
import time
from pathlib import Path

import nefes_ayar
from nefes_ayar import Settings
from nefesd import cgroups
from nefesd.eylem import Config, Daemon, Event
from nefesd.focus import X11Focus
from nefesd.gecmis import EventLog
from nefesd.karar import AppCgroup, Policy
from nefesd.psi import parse_pressure, trigger_line

log = logging.getLogger("nefesd")
PSI_FILE = Path("/proc/pressure/memory")
MB = 1024 * 1024
MIN_POLL_MS = 50  # zaman aşımı 0'a yuvarlanıp döngü CPU yakmasın
MAX_TICK_ERRORS = 20  # üst üste bu kadar tur hatası → dur (finally'de her şey çözülür)
POLL_FAIL = select.POLLERR | select.POLLHUP | select.POLLNVAL
PROTECTED = frozenset({
    "nefes-agent", "xfce4-panel", "xfwm4", "xfdesktop", "xfce4-session",
    "pipewire", "wireplumber", "Xwayland", "gnome-shell",
})


class CgroupOps:
    """eylem.Ops'un gerçek cgroup v2 uygulaması."""

    def __init__(self, root: Path, uid: int) -> None:
        self._root, self._uid = root, uid

    def read_apps(self, frozen_since: dict[str, float]) -> tuple[AppCgroup, ...]:
        return cgroups.read_apps(self._root, self._uid, frozen_since)

    def list_frozen(self) -> tuple[str, ...]:
        return cgroups.list_frozen(self._root, self._uid)

    def freeze(self, path: str) -> None:
        cgroups.freeze(self._root, path, self._uid)

    def thaw(self, path: str) -> None:
        cgroups.thaw(self._root, path, self._uid)

    def reclaim(self, path: str, nbytes: int) -> cgroups.ReclaimResult:
        return cgroups.reclaim(self._root, path, self._uid, nbytes)


class Locked:
    """Hedefin yöntemlerini tek bir kilitle çağırır: Daemon ana döngü ile D-Bus iş parçacığı
    arasında paylaşıldığından durumunu aynı anda iki iş parçacığı değiştirmesin."""

    def __init__(self, target: object, lock: threading.Lock) -> None:
        self._target, self._lock = target, lock

    def __getattr__(self, name: str):
        attr = getattr(self._target, name)
        if not callable(attr):
            return attr

        def locked_call(*args, **kwargs):
            with self._lock:
                return attr(*args, **kwargs)

        return locked_call


def log_event(event: Event) -> None:
    name = event.path.rsplit("/", 1)[-1]
    if event.kind == "frozen":
        log.info("DONDURULDU %s (%d MB kullanıyordu)", name, event.memory_bytes // MB)
    else:
        log.info("DEVAM %s (neden: %s)", name, event.reason)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="nefesd", description="Donma önleyici bellek baskısı servisi")
    p.add_argument("--root", type=Path, default=Path("/sys/fs/cgroup"))
    p.add_argument("--uid", type=int, default=os.getuid())
    p.add_argument("--stall-ms", type=int, default=None,
                   help="pencerede bu kadar bekleme → baskı; verilirse ayar dosyasındaki hassasiyetin "
                        "yerine geçer (150 ms kısa ayırma dalgalarında tetikledi, Deney 03)")
    p.add_argument("--window-ms", type=int, default=2000, help="PSI penceresi (root değilse 2 sn'nin katı)")
    p.add_argument("--max-frozen", type=float, default=None,
                   help="azami dondurma süresi (s); verilirse ayar dosyasının yerine geçer")
    p.add_argument("--settings", type=Path, default=None,
                   help="ayar dosyası (varsayılan ~/.config/nefes/ayarlar.ini)")
    p.add_argument("--cooldown", type=float, default=60.0)
    p.add_argument("--safe-below", type=float, default=5.0,
                   help="some avg10 bunun altında → güvenli (1.0 çözmeyi 30 s+ geciktirdi, Deney 03)")
    p.add_argument("--min-candidate-mb", type=int, default=50)
    p.add_argument("--min-frozen", type=float, default=30.0,
                   help="güvenli baskıda çözmeden önce en az bu kadar donuk kal (s); 2 s'lik gidip gelmeyi önler")
    p.add_argument("--no-dbus", action="store_true", help="D-Bus servisini başlatma (yalnızca log)")
    p.add_argument("--thaw-all", action="store_true",
                   help="diskte donuk tüm uygulama scope'larını çöz ve çık (systemd ExecStopPost)")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def background(executor: ThreadPoolExecutor) -> Callable[[Callable[[], None]], None]:
    """Daemon.run_async: işi tek iş parçacıklı kuyruğa atar; beklenmeyen hata kaybolmasın diye loglar."""

    def report(future: Future) -> None:
        if not future.cancelled() and future.exception() is not None:
            log.error("arka plan işi başarısız", exc_info=future.exception())

    def submit(job: Callable[[], None]) -> None:
        executor.submit(job).add_done_callback(report)

    return submit


def settings_path(args: argparse.Namespace) -> Path:
    return args.settings or nefes_ayar.config_path()


def effective(args: argparse.Namespace, settings: Settings) -> tuple[int, float, frozenset[str]]:
    """(stall_ms, azami donma s, korunan adlar): açıkça verilen komut satırı değeri dosyadan önceliklidir;
    kullanıcının "asla dondurma" listesi yerleşik korunan listeye yalnızca eklenir."""
    stall = args.stall_ms if args.stall_ms is not None else settings.stall_ms
    max_frozen = args.max_frozen if args.max_frozen is not None else settings.max_frozen_seconds
    return stall, max_frozen, PROTECTED | frozenset(settings.never_freeze)


def build_config(args: argparse.Namespace, settings: Settings) -> Config:
    _stall, max_frozen, protected = effective(args, settings)
    return Config(
        policy=Policy(uid=args.uid, protected_names=protected,
                      max_frozen_seconds=max_frozen,
                      min_candidate_bytes=args.min_candidate_mb * MB,
                      min_frozen_seconds=args.min_frozen),
        cooldown_seconds=args.cooldown,
        safe_below=args.safe_below,
        safe_check_seconds=2.0,
    )


def build_daemon(args: argparse.Namespace,
                 settings: Settings = Settings(),
                 run_async: Callable[[Callable[[], None]], None] | None = None,
                 notify: Callable[[Event], None] = log_event,
                 on_status: Callable[[bool, str], None] | None = None,
                 focus: Callable[[], tuple[str | None, bool]] | None = None) -> Daemon:
    return Daemon(build_config(args, settings), CgroupOps(args.root, args.uid), clock=time.monotonic,
                  focus=focus or X11Focus(), notify=notify, run_async=run_async,
                  on_status=on_status, enabled=settings.enabled)


class Controller:
    """D-Bus denetleyicisi: kilitli daemon + olay geçmişi + ayar yeniden yükleme (ADR-0004).
    D-Bus iş parçacığından çağrılır; PSI tetikleyicisini yeniden kurma isteği ana döngüye bırakılır."""

    def __init__(self, daemon, args: argparse.Namespace, settings: Settings, events: EventLog,
                 wake: Callable[[], None] = lambda: None) -> None:
        self._daemon, self._args, self._events, self._wake = daemon, args, events, wake
        self._rearm_lock = threading.Lock()
        self._stall_ms = effective(args, settings)[0]
        self._rearm: int | None = None

    def resume(self, path: str) -> bool:
        return self._daemon.resume(path)

    def frozen_durations(self) -> tuple[tuple[str, float], ...]:
        return self._daemon.frozen_durations()

    def status(self) -> tuple[bool, str, float]:
        return self._daemon.status()

    def set_enabled(self, enabled: bool) -> None:
        self._daemon.set_enabled(enabled)

    def recent_events(self) -> tuple[tuple[int, str, str, str], ...]:
        return self._events.items()

    def reload_settings(self) -> tuple[bool, str]:
        """Bozuk alan varsa hiçbir şey uygulanmaz (eski ayarlar kalır) ve neden döner."""
        settings, warnings = nefes_ayar.load(settings_path(self._args))
        if warnings:
            return False, "; ".join(warnings)
        self._daemon.reconfigure(build_config(self._args, settings))
        self._daemon.set_enabled(settings.enabled)
        stall = effective(self._args, settings)[0]
        need_wake = False
        with self._rearm_lock:
            if stall != self._stall_ms:
                self._stall_ms = self._rearm = stall
                need_wake = True
        if need_wake:
            self._wake()  # ana döngü boşta süresiz bekliyor olabilir
        log.info("ayarlar yeniden yüklendi: %s", settings)
        return True, ""

    def take_rearm(self) -> int | None:
        """Ana döngü için: yeni stall_ms istendiyse bir kez döndürür."""
        with self._rearm_lock:
            stall, self._rearm = self._rearm, None
        return stall


def start_dbus(controller: object, listeners: list[Callable[[Event], None]],
               status_listeners: list[Callable[[bool, str], None]]) -> Callable[[], None] | None:
    """D-Bus servisini oturum veriyolunda başlatır; veriyolu yoksa servis D-Bus'sız sürer."""
    try:
        from nefesd import dbus_servis
    except (ImportError, ValueError) as exc:  # python3-gi yok
        log.warning("D-Bus devre dışı (PyGObject yok): %s", exc)
        return None
    service = dbus_servis.NefesService(controller)
    listeners.append(service.emit)
    status_listeners.append(service.emit_status)
    return dbus_servis.start(service)


def short_name(path: str) -> str:
    try:
        from nefesd.dbus_servis import app_name
    except (ImportError, ValueError):
        return path.rsplit("/", 1)[-1]
    return app_name(path)


def open_trigger(stall_ms: int, window_ms: int) -> int:
    fd = os.open(PSI_FILE, os.O_RDWR | os.O_NONBLOCK)
    os.write(fd, trigger_line("some", stall_ms * 1000, window_ms * 1000))
    return fd


def poll_ms(seconds: float | None) -> int | None:
    """Daemon.poll_timeout() (saniye) → poll() milisaniyesi; yukarı yuvarlar, alt sınır MIN_POLL_MS."""
    if seconds is None:
        return None
    return max(MIN_POLL_MS, math.ceil(seconds * 1000))


def run(args: argparse.Namespace) -> int:
    reclaimer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nefes-reclaim")
    settings, warnings = nefes_ayar.load(settings_path(args))
    for warning in warnings:
        log.warning("ayar: %s", warning)
    events = EventLog()
    listeners: list[Callable[[Event], None]] = [log_event, lambda e: events.record(e, short_name(e.path))]
    status_listeners: list[Callable[[bool, str], None]] = []

    def notify(event: Event) -> None:
        for listener in listeners:
            listener(event)

    def on_status(enabled: bool, level: str) -> None:
        for listener in status_listeners:
            listener(enabled, level)

    daemon = Locked(build_daemon(args, settings, run_async=background(reclaimer), notify=notify,
                                 on_status=on_status), threading.Lock())
    wake_r, wake_w = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)

    def wake() -> None:
        try:
            os.write(wake_w, b"x")
        except BlockingIOError:
            pass  # boru dolu: ana döngü zaten uyanacak

    controller = Controller(daemon, args, settings, events, wake=wake)
    stop_dbus = start_dbus(controller, listeners, status_listeners) if not args.no_dbus else None
    stall_ms = effective(args, settings)[0]
    fd = open_trigger(stall_ms, args.window_ms)
    poller = select.poll()
    poller.register(fd, select.POLLPRI)
    poller.register(wake_r, select.POLLIN)

    def stop(signum: int, _frame: object) -> None:
        raise SystemExit(0)  # istenen durdurma: 0 → systemd "failed" göstermez (143 gösteriyordu)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    daemon.startup()
    log.info("nefesd başladı (uid=%d, tetikleyici some %d ms / %d ms, etkin=%s)",
             args.uid, stall_ms, args.window_ms, settings.enabled)
    errors = 0
    try:
        while True:
            rearm = controller.take_rearm()
            if rearm is not None:  # hassasiyet değişti: önce yenisini aç, hata olursa eski fd kalsın
                try:
                    new_fd = open_trigger(rearm, args.window_ms)
                except OSError as exc:
                    log.error("PSI tetikleyicisi yeniden kurulamadı (%d ms): %s", rearm, exc)
                else:
                    poller.unregister(fd)
                    os.close(fd)
                    fd = new_fd
                    poller.register(fd, select.POLLPRI)
                    log.info("PSI tetikleyicisi yeniden kuruldu: some %d ms / %d ms", rearm, args.window_ms)
            polled = poller.poll(poll_ms(daemon.poll_timeout()))
            if any(f == wake_r for f, _ in polled):
                while True:  # uyandırma baytlarını boşalt
                    try:
                        os.read(wake_r, 64)
                    except BlockingIOError:
                        break
                if not any(f == fd for f, _ in polled):
                    continue  # aynı turda PSI olayı da geldiyse onu düşürme
            if any(f == fd and ev & POLL_FAIL for f, ev in polled):
                log.error("PSI tetikleyicisi geçersiz oldu (POLLERR/POLLHUP/POLLNVAL)")
                return 1
            fired = any(f == fd and ev & select.POLLPRI for f, ev in polled)
            try:
                stats = parse_pressure(PSI_FILE.read_text())
                actions = daemon.tick(fired, stats.some_avg10)
            except (OSError, ValueError) as exc:  # tek bir kötü tur servisi düşürmesin
                errors += 1
                log.exception("tur başarısız (%d/%d): %s", errors, MAX_TICK_ERRORS, exc)
                if errors >= MAX_TICK_ERRORS:
                    return 1
                continue
            errors = 0
            if fired or actions:
                log.debug("baskı: tetik=%s some_avg10=%.2f eylem=%s", fired, stats.some_avg10,
                          [type(a).__name__ for a in actions] or "-")
    finally:
        # Kapanırken ikinci bir sinyal çözme döngüsünü yarıda kesmesin.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        reclaimer.shutdown(wait=False, cancel_futures=True)  # bekleyen geri kazanımlar iptal
        daemon.shutdown()  # AppResumed(shutdown) sinyalleri D-Bus kapanmadan gitsin
        if stop_dbus is not None:
            stop_dbus()
        os.close(fd)
        os.close(wake_r)
        os.close(wake_w)
        left = daemon.frozen_paths()
        if left:
            log.error("kapanışta çözülemeyenler: %s", ", ".join(left))
        else:
            log.info("nefesd durdu; dondurulan her şey çözüldü")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(message)s")
    if args.thaw_all:
        thawed, failed = cgroups.thaw_all(args.root, args.uid)
        for path in thawed:
            log.info("çözüldü (thaw-all): %s", path.rsplit("/", 1)[-1])
        for path in failed:
            log.error("çözülemedi (thaw-all): %s", path)
        return 1 if failed else 0
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
