"""__main__ yardımcıları: poll zaman aşımının milisaniyeye çevrilmesi."""
import pytest

from nefesd.__main__ import MIN_POLL_MS, poll_ms


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
