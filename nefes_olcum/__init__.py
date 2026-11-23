"""nefes-olcum — ölçüm araçları: arayüz gecikme probu (M1, M2) ve PSI kaydedici.

M1 — 100 ms aralıklı zamanlayıcının gecikmesi: p99 < 500 ms ve maks < 2 s (Başarı Ölçütleri).
M2 — toplam donma süresi: gecikmenin 1 s'yi aştığı aralıkların toplamı; varsayılan Pardus'a göre
     ≥ %80 azalma beklenir (karşılaştırma ölçüm turunda yapılır).

Bu modül saf mantıktır (sahte saatle test edilir); GLib döngüsü ve dosya düzeni
nefes_olcum/__main__.py içindedir. CSV zamanları monoton saniyedir (tarih yok).
"""
from __future__ import annotations

import csv
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from nefesd.psi import PressureStats

FREEZE_THRESHOLD_MS = 1000.0  # M2: bu gecikmenin üstü "donma" sayılır
M1_P99_LIMIT_MS = 500.0
M1_MAX_LIMIT_MS = 2000.0
PROBE_FILE = "prob.csv"
PSI_FILE = "psi.csv"
PROBE_HEADER = ("t_s", "lateness_ms")


@dataclass(frozen=True)
class Summary:
    samples: int
    p99_ms: float
    max_ms: float
    freeze_total_s: float

    def meets_m1(self) -> bool:
        return self.p99_ms < M1_P99_LIMIT_MS and self.max_ms < M1_MAX_LIMIT_MS


def percentile(values: Sequence[float], p: float) -> float:
    """En yakın sıra (nearest-rank) yöntemiyle yüzdelik."""
    if not values:
        raise ValueError("boş örnek kümesinin yüzdeliği yok")
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


class Probe:
    """Her tetikte, beklenen zamana göre kaç ms geç kalındığını hesaplar.

    Bir donmadan sonra GLib tek bir geciken tetik verir; sonraki beklenen zaman o tetikten
    itibaren sayılır (donma iki kez sayılmaz) — GLib.timeout_add da böyle yeniden kurar.
    """

    def __init__(self, interval_s: float) -> None:
        self._interval = interval_s
        self._expected: float | None = None

    def start(self, now: float) -> None:
        self._expected = now + self._interval

    def tick(self, now: float) -> float:
        if self._expected is None:
            self.start(now)
            return 0.0
        lateness_ms = max(0.0, (now - self._expected) * 1000.0)
        self._expected = now + self._interval
        return lateness_ms


def summarize(lateness_ms: Sequence[float]) -> Summary:
    if not lateness_ms:
        raise ValueError("özetlenecek örnek yok")
    freeze_ms = sum(x for x in lateness_ms if x > FREEZE_THRESHOLD_MS)
    return Summary(
        samples=len(lateness_ms),
        p99_ms=percentile(lateness_ms, 99),
        max_ms=max(lateness_ms),
        freeze_total_s=freeze_ms / 1000.0,
    )


def psi_header() -> tuple[str, ...]:
    return ("t_s", "some_avg10", "some_avg60", "some_total", "full_avg10", "full_avg60", "full_total")


def psi_row(t: float, stats: PressureStats) -> tuple:
    return (t, stats.some_avg10, stats.some_avg60, stats.some_total,
            stats.full_avg10, stats.full_avg60, stats.full_total)


def write_probe_csv(path: Path, rows: Iterable[tuple[float, float]]) -> None:
    _write_csv(path, PROBE_HEADER, rows)


def write_psi_csv(path: Path, rows: Iterable[tuple]) -> None:
    _write_csv(path, psi_header(), rows)


def summarize_run(directory: Path) -> dict:
    """Bir ölçüm klasörünün özeti: prob (M1/M2) ve PSI tepe değerleri."""
    directory = Path(directory)
    lateness = [float(r["lateness_ms"]) for r in _read_csv(directory / PROBE_FILE)]
    psi = list(_read_csv(directory / PSI_FILE))
    return {
        "prob": summarize(lateness),
        "psi_some_avg10_max": max((float(r["some_avg10"]) for r in psi), default=0.0),
        "psi_full_avg10_max": max((float(r["full_avg10"]) for r in psi), default=0.0),
    }


def _write_csv(path: Path, header: Sequence[str], rows: Iterable[tuple]) -> None:
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
