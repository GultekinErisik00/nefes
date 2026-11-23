"""eylem.Daemon birim testleri — sahte saat, sahte cgroup işlemleri, sahte odak.

Daemon'ın sorumluluğu: durum (ne zamandan beri donuk, kim bekleme süresinde), karar motorunun
eylemlerini uygulamak, zaman aşımı/kapanış güvenliği. Aday seçimi karar motorunda test edilir.
"""
import errno

from nefesd.cgroups import ReclaimResult, ScopeGone
from nefesd.eylem import Config, Daemon, Event
from nefesd.karar import AppCgroup, Freeze, Policy, Thaw

MB = 1024 * 1024
APP = "/user.slice/user-1000.slice/user@1000.service/app.slice"
FIREFOX = f"{APP}/app-nefes-firefox-11.scope"
CALC = f"{APP}/app-nefes-libreoffice-12.scope"

CONFIG = Config(
    policy=Policy(uid=1000, protected_names=frozenset({"nefes-agent"}),
                  max_frozen_seconds=600.0, min_candidate_bytes=50 * MB),
    cooldown_seconds=60.0,
    safe_below=1.0,
    safe_check_seconds=2.0,
)


class FakeOps:
    def __init__(self, apps, frozen_on_disk=(), gone=()):
        self.mem = dict(apps)
        self.frozen = set(frozen_on_disk)
        self.gone = set(gone)
        self.fail = {}  # (işlem, yol) -> errno: o işlem o yolda OSError verir
        self.calls = []

    def read_apps(self, frozen_since):
        return tuple(AppCgroup(p, m, frozen_since.get(p)) for p, m in sorted(self.mem.items()))

    def list_frozen(self):
        return tuple(sorted(self.frozen))

    def freeze(self, path):
        self._check("freeze", path)
        self.calls.append(("freeze", path))
        self.frozen.add(path)

    def thaw(self, path):
        self._check("thaw", path)
        self.calls.append(("thaw", path))
        self.frozen.discard(path)

    def reclaim(self, path, nbytes):
        self._check("reclaim", path)
        self.calls.append(("reclaim", path, nbytes))
        return ReclaimResult(nbytes, self.mem[path], 2 * MB, True)

    def _check(self, op, path):
        if path in self.gone:
            raise ScopeGone(path)
        if (op, path) in self.fail:
            raise OSError(self.fail[(op, path)], f"{op} başarısız")


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class Deferred:
    """Arka plan iş kuyruğu yerine geçer: işleri tutar, run() ile çalıştırır."""

    def __init__(self):
        self.jobs = []

    def __call__(self, job):
        self.jobs.append(job)

    def run(self):
        jobs, self.jobs = self.jobs, []
        for job in jobs:
            job()


def make(apps, focus=(None, True), run_async=None, **kw):
    ops, clock, events = FakeOps(apps, **kw), Clock(), []
    extra = {"run_async": run_async} if run_async is not None else {}
    daemon = Daemon(CONFIG, ops, clock=clock, focus=lambda: focus, notify=events.append, **extra)
    return daemon, ops, clock, events


# --- dondurma ----------------------------------------------------------------

def test_high_pressure_freezes_then_reclaims_the_candidate_and_notifies():
    daemon, ops, _, events = make({FIREFOX: 900 * MB, CALC: 300 * MB}, focus=(CALC, True))
    assert daemon.tick(fired=True, some_avg10=30.0) == (Freeze(FIREFOX),)
    assert ops.calls == [("freeze", FIREFOX), ("reclaim", FIREFOX, 900 * MB)]
    assert events == [Event("frozen", FIREFOX, "pressure", 898 * MB)]


def test_frozen_app_is_not_frozen_twice_while_pressure_continues():
    daemon, ops, clock, _ = make({FIREFOX: 900 * MB})
    daemon.tick(fired=True, some_avg10=30.0)
    clock.t += 30
    assert daemon.tick(fired=True, some_avg10=30.0) == ()
    assert ops.calls.count(("freeze", FIREFOX)) == 1


def test_tick_returns_after_freeze_and_reclaim_runs_in_background():
    deferred = Deferred()
    daemon, ops, _, events = make({FIREFOX: 900 * MB}, run_async=deferred)
    assert daemon.tick(fired=True, some_avg10=30.0) == (Freeze(FIREFOX),)
    assert ops.calls == [("freeze", FIREFOX)]  # reclaim henüz yok: döngü bloklanmadı
    assert daemon.frozen_paths() == (FIREFOX,)
    assert events == []
    deferred.run()
    assert ops.calls[-1] == ("reclaim", FIREFOX, 900 * MB)
    assert events == [Event("frozen", FIREFOX, "pressure", 898 * MB)]


def test_background_reclaim_of_an_app_that_exited_neither_crashes_nor_notifies():
    deferred = Deferred()
    daemon, ops, _, events = make({FIREFOX: 900 * MB}, run_async=deferred)
    daemon.tick(fired=True, some_avg10=30.0)
    ops.gone.add(FIREFOX)
    deferred.run()
    assert events == []


def test_background_reclaim_error_still_notifies_with_zero_reclaimed():
    deferred = Deferred()
    daemon, ops, _, events = make({FIREFOX: 900 * MB}, run_async=deferred)
    daemon.tick(fired=True, some_avg10=30.0)
    ops.fail[("reclaim", FIREFOX)] = errno.EIO
    deferred.run()
    assert events == [Event("frozen", FIREFOX, "pressure", 0)]
    assert daemon.frozen_paths() == (FIREFOX,)


def test_scope_that_exits_during_freeze_is_ignored():
    daemon, ops, _, events = make({FIREFOX: 900 * MB}, gone={FIREFOX})
    daemon.tick(fired=True, some_avg10=30.0)
    assert events == []
    assert daemon.frozen_paths() == ()


# --- çözme -------------------------------------------------------------------

def test_timeout_thaws_and_starts_cooldown_that_blocks_immediate_refreeze():
    daemon, ops, clock, events = make({FIREFOX: 900 * MB})
    daemon.tick(fired=True, some_avg10=30.0)
    clock.t += 601
    assert daemon.tick(fired=False, some_avg10=30.0) == (Thaw(FIREFOX, "timeout"),)
    assert events[-1] == Event("resumed", FIREFOX, "timeout", 0)
    clock.t += 10  # bekleme süresi (60 s) dolmadı
    assert daemon.tick(fired=True, some_avg10=30.0) == ()


def test_app_can_be_frozen_again_after_cooldown_ends():
    daemon, ops, clock, _ = make({FIREFOX: 900 * MB})
    daemon.tick(fired=True, some_avg10=30.0)
    clock.t += 601
    daemon.tick(fired=False, some_avg10=30.0)
    clock.t += 61
    assert daemon.tick(fired=True, some_avg10=30.0) == (Freeze(FIREFOX),)


def test_safe_pressure_thaws_frozen_app():
    daemon, ops, clock, events = make({FIREFOX: 900 * MB})
    daemon.tick(fired=True, some_avg10=30.0)
    clock.t += 5
    assert daemon.tick(fired=False, some_avg10=0.2) == (Thaw(FIREFOX, "pressure_low"),)
    assert daemon.frozen_paths() == ()
    assert events[-1] == Event("resumed", FIREFOX, "pressure_low", 0)


# --- hata yolları: hiçbir uygulama takipsiz donuk kalmamalı --------------------

def test_failed_thaw_keeps_app_tracked_and_is_retried_next_tick():
    daemon, ops, clock, _ = make({FIREFOX: 900 * MB})
    daemon.tick(fired=True, some_avg10=30.0)
    clock.t += 601
    ops.fail[("thaw", FIREFOX)] = errno.EBUSY
    daemon.tick(fired=False, some_avg10=30.0)  # çökmemeli
    assert daemon.frozen_paths() == (FIREFOX,)
    del ops.fail[("thaw", FIREFOX)]
    clock.t += 1
    daemon.tick(fired=False, some_avg10=30.0)
    assert daemon.frozen_paths() == () and FIREFOX not in ops.frozen


def test_failed_thaw_does_not_stop_other_actions_in_the_same_tick():
    daemon, ops, clock, _ = make({FIREFOX: 900 * MB, CALC: 300 * MB})
    daemon.tick(fired=True, some_avg10=30.0)  # FIREFOX donar
    clock.t += 601
    ops.fail[("thaw", FIREFOX)] = errno.EBUSY
    daemon.tick(fired=True, some_avg10=30.0)  # FIREFOX çözülemez, CALC yine dondurulmalı
    assert ("freeze", CALC) in ops.calls


def test_shutdown_continues_after_one_thaw_fails():
    daemon, ops, clock, _ = make({FIREFOX: 900 * MB, CALC: 300 * MB})
    daemon.tick(fired=True, some_avg10=30.0)
    daemon.tick(fired=True, some_avg10=30.0)  # ikisi de donuk
    ops.fail[("thaw", FIREFOX)] = errno.EBUSY
    daemon.shutdown()
    assert CALC not in ops.frozen


def test_failed_freeze_is_not_tracked_and_is_undone():
    daemon, ops, _, events = make({FIREFOX: 900 * MB})
    ops.fail[("freeze", FIREFOX)] = errno.EBUSY
    daemon.tick(fired=True, some_avg10=30.0)
    assert daemon.frozen_paths() == ()
    assert ("thaw", FIREFOX) in ops.calls  # yarım kalmış dondurma geri alınır
    assert events == []


def test_failed_reclaim_still_tracks_and_notifies_the_frozen_app():
    daemon, ops, _, events = make({FIREFOX: 900 * MB})
    ops.fail[("reclaim", FIREFOX)] = errno.EINVAL
    daemon.tick(fired=True, some_avg10=30.0)
    assert daemon.frozen_paths() == (FIREFOX,)
    assert events == [Event("frozen", FIREFOX, "pressure", 0)]


def test_startup_continues_past_scopes_that_fail_to_thaw():
    daemon, ops, _, _ = make({FIREFOX: 900 * MB, CALC: 300 * MB}, frozen_on_disk={FIREFOX, CALC})
    ops.fail[("thaw", CALC)] = errno.EBUSY
    daemon.startup()
    assert FIREFOX not in ops.frozen


def test_user_resume_thaws_only_apps_this_daemon_froze():
    daemon, ops, _, events = make({FIREFOX: 900 * MB, CALC: 300 * MB})
    daemon.tick(fired=True, some_avg10=30.0)
    assert daemon.resume(CALC) is False
    assert daemon.resume(FIREFOX) is True
    assert ("thaw", FIREFOX) in ops.calls and ("thaw", CALC) not in ops.calls
    assert events[-1] == Event("resumed", FIREFOX, "user", 0)


def test_exited_frozen_app_is_forgotten():
    daemon, ops, _, _ = make({FIREFOX: 900 * MB})
    daemon.tick(fired=True, some_avg10=30.0)
    del ops.mem[FIREFOX]  # uygulama kapandı
    daemon.tick(fired=False, some_avg10=30.0)
    assert daemon.frozen_paths() == ()


# --- başlangıç / kapanış güvenliği --------------------------------------------

def test_startup_thaws_scopes_left_frozen_by_a_previous_run():
    daemon, ops, _, _ = make({FIREFOX: 900 * MB}, frozen_on_disk={FIREFOX})
    daemon.startup()
    assert ops.calls == [("thaw", FIREFOX)]


def test_shutdown_thaws_everything_this_daemon_froze():
    daemon, ops, _, _ = make({FIREFOX: 900 * MB, CALC: 300 * MB})
    daemon.tick(fired=True, some_avg10=30.0)
    daemon.shutdown()
    assert ops.frozen == set()
    assert daemon.frozen_paths() == ()


# --- poll zaman aşımı ---------------------------------------------------------

def test_poll_timeout_blocks_forever_when_nothing_is_frozen():
    daemon, _, _, _ = make({FIREFOX: 900 * MB})
    assert daemon.poll_timeout() is None


def test_poll_timeout_wakes_for_safe_checks_while_something_is_frozen():
    daemon, _, _, _ = make({FIREFOX: 900 * MB})
    daemon.tick(fired=True, some_avg10=30.0)
    assert daemon.poll_timeout() == 2.0


def test_poll_timeout_wakes_exactly_at_the_freeze_deadline_when_it_is_sooner():
    daemon, _, clock, _ = make({FIREFOX: 900 * MB})
    daemon.tick(fired=True, some_avg10=30.0)
    clock.t += 599.5
    assert daemon.poll_timeout() == 0.5
    clock.t += 10
    assert daemon.poll_timeout() == 0.0
