"""nefes_olcum birim testleri — gecikme probu, M1/M2 özeti, CSV.

M1: 100 ms'lik zamanlayıcının gecikmesi (p99 < 500 ms, maks < 2 s).
M2: gecikmenin 1 s'yi aştığı aralıkların toplamı (toplam donma süresi).
Beklenen değerler elle hesaplanmış sabitlerdir.
"""
import pytest

from nefes_olcum import (
    Probe,
    Summary,
    percentile,
    psi_header,
    psi_row,
    summarize,
    summarize_run,
    write_probe_csv,
    write_psi_csv,
)
from nefesd.psi import PressureStats


# --- yüzdelik (en yakın sıra yöntemi) ---------------------------------------------

def test_percentile_uses_nearest_rank():
    values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert percentile(values, 50) == 50
    assert percentile(values, 99) == 100
    assert percentile(values, 90) == 90


def test_percentile_of_a_single_value_is_that_value():
    assert percentile([7.5], 99) == 7.5


def test_percentile_of_nothing_is_an_error():
    with pytest.raises(ValueError):
        percentile([], 99)


# --- prob ------------------------------------------------------------------------

def test_probe_reports_how_late_each_tick_fires():
    probe = Probe(interval_s=0.1)
    probe.start(0.0)
    assert probe.tick(0.1) == pytest.approx(0.0)
    assert probe.tick(0.25) == pytest.approx(50.0)  # beklenen 0.2


def test_probe_does_not_count_a_stall_twice():
    # 3 s donma: GLib geciken tek bir tetik verir; sonraki beklenen zaman o andan itibaren sayılır
    probe = Probe(interval_s=0.1)
    probe.start(0.0)
    assert probe.tick(3.1) == pytest.approx(3000.0)
    assert probe.tick(3.2) == pytest.approx(0.0)


def test_probe_never_reports_negative_lateness():
    probe = Probe(interval_s=0.1)
    probe.start(0.0)
    assert probe.tick(0.09) == 0.0  # erken tetik (zamanlayıcı yuvarlaması)


# --- özet (M1, M2) -------------------------------------------------------------------

def test_summary_reports_p99_max_and_total_freeze():
    lateness = [0.0] * 98 + [600.0, 2500.0]
    assert summarize(lateness) == Summary(samples=100, p99_ms=600.0, max_ms=2500.0, freeze_total_s=2.5)


def test_freeze_total_counts_only_stalls_longer_than_one_second():
    s = summarize([1200.0, 900.0, 3000.0, 1000.0])
    assert s.freeze_total_s == pytest.approx(4.2)  # 1200 + 3000; tam 1000 sayılmaz


def test_m1_target_is_p99_below_500_and_max_below_2000():
    assert Summary(100, 499.0, 1999.0, 0.0).meets_m1() is True
    assert Summary(100, 500.0, 100.0, 0.0).meets_m1() is False
    assert Summary(100, 10.0, 2000.0, 2.0).meets_m1() is False


def test_summary_of_no_samples_is_an_error():
    with pytest.raises(ValueError):
        summarize([])


# --- CSV ------------------------------------------------------------------------------

def test_psi_row_has_one_value_per_header_column():
    stats = PressureStats(12.5, 3.25, 578489, 4.0, 1.0, 120001)
    row = psi_row(42.0, stats)
    assert len(row) == len(psi_header())
    assert row == (42.0, 12.5, 3.25, 578489, 4.0, 1.0, 120001)


def test_run_directory_round_trip_gives_the_same_summary(tmp_path):
    lateness = [0.0] * 98 + [600.0, 2500.0]
    write_probe_csv(tmp_path / "prob.csv", [(i * 0.1, lat) for i, lat in enumerate(lateness)])
    write_psi_csv(tmp_path / "psi.csv", [
        psi_row(0.0, PressureStats(1.0, 0.5, 10, 0.0, 0.0, 0)),
        psi_row(1.0, PressureStats(35.2, 10.0, 99, 12.0, 3.0, 50)),
    ])
    result = summarize_run(tmp_path)
    assert result["prob"] == Summary(100, 600.0, 2500.0, 2.5)
    assert result["psi_some_avg10_max"] == 35.2
    assert result["psi_full_avg10_max"] == 12.0
