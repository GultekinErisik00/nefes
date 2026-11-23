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
