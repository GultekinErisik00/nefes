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

from nefesd import cgroups
from nefesd.eylem import Config, Daemon, Event
from nefesd.focus import X11Focus
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
    p.add_argument("--stall-ms", type=int, default=300,
                   help="pencerede bu kadar bekleme → baskı (150 ms kısa ayırma dalgalarında tetikledi, Deney 03)")
    p.add_argument("--window-ms", type=int, default=2000, help="PSI penceresi (root değilse 2 sn'nin katı)")
    p.add_argument("--max-frozen", type=float, default=600.0, help="azami dondurma süresi (s)")
    p.add_argument("--cooldown", type=float, default=60.0)
    p.add_argument("--safe-below", type=float, default=5.0,
                   help="some avg10 bunun altında → güvenli (1.0 çözmeyi 30 s+ geciktirdi, Deney 03)")
    p.add_argument("--min-candidate-mb", type=int, default=50)
    p.add_argument("--no-dbus", action="store_true", help="D-Bus servisini başlatma (yalnızca log)")
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


def build_daemon(args: argparse.Namespace,
                 run_async: Callable[[Callable[[], None]], None] | None = None,
                 notify: Callable[[Event], None] = log_event) -> Daemon:
    config = Config(
        policy=Policy(uid=args.uid, protected_names=PROTECTED,
                      max_frozen_seconds=args.max_frozen,
                      min_candidate_bytes=args.min_candidate_mb * MB),
        cooldown_seconds=args.cooldown,
        safe_below=args.safe_below,
        safe_check_seconds=2.0,
    )
    return Daemon(config, CgroupOps(args.root, args.uid), clock=time.monotonic,
                  focus=X11Focus(), notify=notify, run_async=run_async)


def start_dbus(controller: object, listeners: list[Callable[[Event], None]]) -> Callable[[], None] | None:
    """D-Bus servisini oturum veriyolunda başlatır; veriyolu yoksa servis D-Bus'sız sürer."""
    try:
        from nefesd import dbus_servis
    except (ImportError, ValueError) as exc:  # python3-gi yok
        log.warning("D-Bus devre dışı (PyGObject yok): %s", exc)
        return None
    service = dbus_servis.NefesService(controller)
    listeners.append(service.emit)
    return dbus_servis.start(service)


def poll_ms(seconds: float | None) -> int | None:
    """Daemon.poll_timeout() (saniye) → poll() milisaniyesi; yukarı yuvarlar, alt sınır MIN_POLL_MS."""
    if seconds is None:
        return None
    return max(MIN_POLL_MS, math.ceil(seconds * 1000))


def run(args: argparse.Namespace) -> int:
    reclaimer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nefes-reclaim")
    listeners: list[Callable[[Event], None]] = [log_event]

    def notify(event: Event) -> None:
        for listener in listeners:
            listener(event)

    daemon = Locked(build_daemon(args, run_async=background(reclaimer), notify=notify), threading.Lock())
    stop_dbus = start_dbus(daemon, listeners) if not args.no_dbus else None
    fd = os.open(PSI_FILE, os.O_RDWR | os.O_NONBLOCK)
    os.write(fd, trigger_line("some", args.stall_ms * 1000, args.window_ms * 1000))
    poller = select.poll()
    poller.register(fd, select.POLLPRI)

    def stop(signum: int, _frame: object) -> None:
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    daemon.startup()
    log.info("nefesd başladı (uid=%d, tetikleyici some %d ms / %d ms)", args.uid, args.stall_ms, args.window_ms)
    errors = 0
    try:
        while True:
            events = poller.poll(poll_ms(daemon.poll_timeout()))
            if any(ev & POLL_FAIL for _, ev in events):
                log.error("PSI tetikleyicisi geçersiz oldu (POLLERR/POLLHUP/POLLNVAL)")
                return 1
            fired = any(ev & select.POLLPRI for _, ev in events)
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
        left = daemon.frozen_paths()
        if left:
            log.error("kapanışta çözülemeyenler: %s", ", ".join(left))
        else:
            log.info("nefesd durdu; dondurulan her şey çözüldü")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(message)s")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
