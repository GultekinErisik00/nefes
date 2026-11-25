"""__main__ yardımcıları: poll zaman aşımı ve iş parçacıkları arası kilitli vekil."""
import threading

import pytest

from nefesd.__main__ import MIN_POLL_MS, Locked, poll_ms


def test_locked_proxy_calls_the_target_while_holding_the_lock():
    lock = threading.Lock()
    seen = []

    class Target:
        def double(self, x):
            seen.append(lock.locked())
            return x * 2

    assert Locked(Target(), lock).double(21) == 42
    assert seen == [True]
    assert not lock.locked()


def test_locked_proxy_releases_the_lock_when_the_target_raises():
    lock = threading.Lock()

    class Target:
        def boom(self):
            raise OSError("x")

    with pytest.raises(OSError):
        Locked(Target(), lock).boom()
    assert not lock.locked()


@pytest.mark.parametrize(
    "seconds, expected",
    [
        (None, None),  # donuk yok: sonsuza dek bekle
        (2.0, 2000),
        (0.0004, MIN_POLL_MS),  # 0'a yuvarlanıp döngüyü meşgul etmesin
        (0.0, MIN_POLL_MS),
        (0.1234, 124),  # aşağı değil yukarı yuvarla: son tarihten önce uyanmasın
    ],
)
def test_poll_ms_converts_seconds_without_busy_looping(seconds, expected):
    assert poll_ms(seconds) == expected


# --- ayar dosyası ve yeniden yükleme (arayüz, ADR-0004) ---------------------------------

from nefes_ayar import Settings, save  # noqa: E402
from nefesd.__main__ import PROTECTED, Controller, build_daemon, effective, parse_args  # noqa: E402
from nefesd.gecmis import EventLog  # noqa: E402


def test_effective_uses_settings_when_cli_not_given():
    settings = Settings(sensitivity="az", max_frozen_min=20, never_freeze=("vlc",))
    assert effective(parse_args([]), settings) == (500, 1200.0, PROTECTED | {"vlc"})


def test_cli_overrides_settings():
    args = parse_args(["--stall-ms", "150", "--max-frozen", "60"])
    stall, max_frozen, _ = effective(args, Settings(sensitivity="az", max_frozen_min=20))
    assert (stall, max_frozen) == (150, 60.0)


def test_never_freeze_only_adds_to_protected():
    _, _, protected = effective(parse_args([]), Settings(never_freeze=("xfwm4", "vlc")))
    assert PROTECTED <= protected and "vlc" in protected


class FakeDaemon:
    def __init__(self):
        self.configs, self.enabled = [], []

    def reconfigure(self, config):
        self.configs.append(config)

    def set_enabled(self, enabled):
        self.enabled.append(enabled)


def make_controller(tmp_path, settings=Settings(), argv=()):
    path = tmp_path / "ayarlar.ini"
    save(path, settings)
    args = parse_args([*argv, "--settings", str(path)])
    daemon = FakeDaemon()
    return Controller(daemon, args, settings, EventLog()), daemon, path


def test_reload_invalid_keeps_previous_settings(tmp_path):
    controller, daemon, path = make_controller(tmp_path)
    path.write_text("[nefes]\nhassasiyet = cokcok\n", encoding="utf-8")
    ok, message = controller.reload_settings()
    assert ok is False and "hassasiyet" in message
    assert daemon.configs == [] and daemon.enabled == []
    assert controller.take_rearm() is None


def test_reload_valid_reconfigures_and_requests_rearm_when_stall_changes(tmp_path):
    controller, daemon, path = make_controller(tmp_path)
    save(path, Settings(enabled=False, sensitivity="cok", max_frozen_min=5, never_freeze=("vlc",)))
    assert controller.reload_settings() == (True, "")
    config = daemon.configs[-1]
    assert config.policy.max_frozen_seconds == 300.0 and "vlc" in config.policy.protected_names
    assert daemon.enabled == [False]
    assert controller.take_rearm() == 200
    assert controller.take_rearm() is None  # istek bir kez alınır


def test_reload_with_same_stall_does_not_request_rearm(tmp_path):
    controller, _, path = make_controller(tmp_path)
    save(path, Settings(max_frozen_min=30))
    assert controller.reload_settings() == (True, "")
    assert controller.take_rearm() is None


def test_cli_stall_ms_is_kept_across_reload(tmp_path):
    controller, _, path = make_controller(tmp_path, argv=("--stall-ms", "150"))
    save(path, Settings(sensitivity="az"))
    controller.reload_settings()
    assert controller.take_rearm() is None


def test_startup_with_disabled_settings_does_not_freeze(tmp_path):
    args = parse_args(["--root", str(tmp_path), "--uid", "1000"])
    daemon = build_daemon(args, Settings(enabled=False), focus=lambda: (None, True))
    assert daemon.tick(True, 80.0) == ()


def test_rearm_request_wakes_the_main_loop(tmp_path):
    """VM'de bulundu (25 Kas): boşta poll() süresiz bekler → hassasiyet değişikliği uygulanmıyordu."""
    path = tmp_path / "ayarlar.ini"
    save(path, Settings())
    woken = []
    controller = Controller(FakeDaemon(), parse_args(["--settings", str(path)]), Settings(),
                            EventLog(), wake=lambda: woken.append(True))
    save(path, Settings(sensitivity="cok"))
    controller.reload_settings()
    assert woken == [True]


def test_reload_rejects_broad_never_freeze_name(tmp_path):
    """I3: 'nefes' gibi genel bir ad tüm app-nefes-*.scope'ları koruyup Nefes'i etkisizleştiremez."""
    controller, daemon, path = make_controller(tmp_path)
    path.write_text("[nefes]\nasla_dondurma = nefes\n", encoding="utf-8")
    ok, message = controller.reload_settings()
    assert ok is False and "asla_dondurma" in message
    assert daemon.configs == []
