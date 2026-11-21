"""psi.py birim testleri — ayrıştırma, tetikleyici satırı ve seviye sınıflandırması."""
import pytest

from nefesd.karar import Pressure
from nefesd.psi import PressureStats, classify, parse_pressure, trigger_line

SAMPLE = (
    "some avg10=12.50 avg60=3.25 avg300=0.80 total=578489\n"
    "full avg10=4.00 avg60=1.00 avg300=0.10 total=120001\n"
)


def test_parse_pressure_reads_some_and_full_lines():
    assert parse_pressure(SAMPLE) == PressureStats(
        some_avg10=12.5, some_avg60=3.25, some_total=578489,
        full_avg10=4.0, full_avg60=1.0, full_total=120001,
    )


@pytest.mark.parametrize(
    "text",
    [
        "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n",  # some satırı yok
        "",  # boş
        "some avg10=0.00 avg60 avg300=0.00 total=0\n",  # '=' olmayan parça
        "some avg10=0.00 avg300=0.00 total=0\n",  # avg60 eksik
        "some avg10=abc avg60=0.00 avg300=0.00 total=0\n",  # sayı değil
        "some avg10=nan avg60=0.00 avg300=0.00 total=0\n",  # NaN
    ],
)
def test_parse_pressure_rejects_malformed_text_with_value_error(text):
    with pytest.raises(ValueError):
        parse_pressure(text)


def test_parse_pressure_without_full_line_reports_zero_full():
    stats = parse_pressure("some avg10=1.50 avg60=0.50 avg300=0.10 total=42\n")
    assert (stats.some_avg10, stats.full_avg10, stats.full_total) == (1.5, 0.0, 0)


def test_parse_pressure_ignores_unknown_lines():
    stats = parse_pressure("weird line\n" + SAMPLE)
    assert stats.some_total == 578489


@pytest.mark.parametrize(
    "kind, stall_us, window_us, expected",
    [
        ("some", 150_000, 1_000_000, b"some 150000 1000000\0"),
        ("full", 500_000, 2_000_000, b"full 500000 2000000\0"),
        ("some", 500_000, 500_000, b"some 500000 500000\0"),  # pencere alt sınırı, stall = pencere
        ("some", 1, 10_000_000, b"some 1 10000000\0"),  # pencere üst sınırı
    ],
)
def test_trigger_line_formats_kernel_trigger(kind, stall_us, window_us, expected):
    assert trigger_line(kind, stall_us, window_us) == expected


@pytest.mark.parametrize(
    "kind, stall_us, window_us",
    [
        ("avg", 150_000, 1_000_000),  # geçersiz tür
        ("some", 150_000, 499_999),  # pencere < 500 ms
        ("some", 150_000, 10_000_001),  # pencere > 10 s
        ("some", 1_000_001, 1_000_000),  # stall > pencere
        ("some", 0, 1_000_000),  # stall sıfır
        ("some", -5, 1_000_000),  # stall negatif
        ("some", True, 1_000_000),  # bool tamsayı değildir
        ("some", 1.5, 1_000_000),  # ondalıklı
    ],
)
def test_trigger_line_rejects_values_the_kernel_would_refuse(kind, stall_us, window_us):
    with pytest.raises(ValueError):
        trigger_line(kind, stall_us, window_us)


def test_classify_is_high_when_trigger_fired():
    assert classify(fired=True, some_avg10=0.0, safe_below=1.0) is Pressure.HIGH


def test_classify_is_high_when_trigger_fired_with_high_average():
    assert classify(fired=True, some_avg10=40.0, safe_below=1.0) is Pressure.HIGH


def test_classify_is_safe_when_quiet_and_below_threshold():
    assert classify(fired=False, some_avg10=0.99, safe_below=1.0) is Pressure.SAFE


def test_classify_is_normal_when_quiet_but_at_or_above_threshold():
    assert classify(fired=False, some_avg10=1.0, safe_below=1.0) is Pressure.NORMAL
