"""nefes_agent.gorunum — simge durumu ve pencere metinleri (saf, arayüz 2026-11-25)."""
from datetime import timezone

import pytest

from nefes_agent.gorunum import (
    REASON_TEXT,
    event_line,
    format_duration,
    format_mb,
    sparkline,
    tray_state,
)

MB = 1024 * 1024


@pytest.mark.parametrize("service_up, enabled, level, frozen, expected", [
    (False, True, "high", 2, ("nefes-kapali", "Nefes çalışmıyor")),
    (True, False, "high", 0, ("nefes-duraklatildi", "Nefes duraklatıldı")),
    (True, True, "high", 2, ("nefes-donuk", "Nefes açık — 2 uygulama donduruldu")),
    (True, True, "safe", 1, ("nefes-donuk", "Nefes açık — 1 uygulama donduruldu")),
    (True, True, "high", 0, ("nefes-baski", "Nefes açık — baskı yüksek")),
    (True, True, "normal", 0, ("nefes-normal", "Nefes açık — baskı orta")),
    (True, True, "safe", 0, ("nefes-normal", "Nefes açık — baskı düşük")),
])
def test_tray_state(service_up, enabled, level, frozen, expected):
    assert tray_state(service_up, enabled, level, frozen) == expected


@pytest.mark.parametrize("nbytes, text", [
    (0, "0 MB"), (420 * MB, "420 MB"), (1023 * MB, "1023 MB"),
    (1024 * MB, "1,0 GB"), (int(1.43 * 1024 * MB), "1,4 GB"),
])
def test_format_mb(nbytes, text):
    assert format_mb(nbytes) == text


@pytest.mark.parametrize("seconds, text", [
    (0, "0 sn"), (40, "40 sn"), (59, "59 sn"), (60, "1 dk"), (185, "3 dk"),
    (3600, "1 sa"), (3900, "1 sa 5 dk"),
])
def test_format_duration(seconds, text):
    assert format_duration(seconds) == text


def test_event_line():
    t = 1700000000 - 1700000000 % 86400 + 14 * 3600 + 2 * 60  # 14:02 UTC
    assert event_line(t, "frozen", "firefox-esr", "pressure", tz=timezone.utc) == \
        "14:02 Firefox donduruldu (baskı yüksek)"
    assert event_line(t, "resumed", "calc", "user", tz=timezone.utc) == \
        "14:02 Calc devam ettirildi (sen)"
    assert event_line(t, "resumed", "calc", "yeni-neden", tz=timezone.utc) == \
        "14:02 Calc devam ettirildi (çözüldü)"


def test_reason_text_covers_every_contract_reason():
    for reason in ("pressure", "user", "focus", "timeout", "pressure_low", "paused", "shutdown"):
        assert reason in REASON_TEXT


def test_sparkline():
    assert sparkline([]) == ""
    assert sparkline([0, 50, 100]) == "▁▅█"
    assert sparkline([200, -5]) == "█▁"  # aralık dışı kırpılır
    assert len(sparkline(list(range(100)), width=60)) == 60


def test_app_choice_reads_name_and_scope_program_name():
    from nefes_agent.gorunum import app_choice
    text = "[Desktop Entry]\nName=VLC media player\nName[tr]=VLC ortam oynatıcısı\nExec=/usr/bin/vlc --started-from-file %U\n"
    assert app_choice(text) == ("VLC media player", "vlc")
    assert app_choice("[Desktop Entry]\nName=X\nExec=env LANG=C GIMP-2.10 %U\n") == ("X", "gimp-2-10")
    wrapped = "[Desktop Entry]\nName=Firefox\nExec=/usr/bin/nefes-baslat /usr/lib/firefox-esr/firefox-esr %u\n"
    assert app_choice(wrapped) == ("Firefox", "firefox-esr")  # sarmalayıcı atlanır
    assert app_choice("[Desktop Entry]\nName=Y\n") is None
