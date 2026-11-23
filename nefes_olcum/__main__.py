"""python3 -m nefes_olcum — ölçüm komutları.

  python3 -m nefes_olcum kaydet --cikti olcumler/nefes-1 --sure 60   # prob + PSI kaydı
  python3 -m nefes_olcum ozet olcumler/varsayilan-1 olcumler/nefes-1  # karşılaştırmalı özet

Prob GLib ana döngüsünde 100 ms'lik bir zamanlayıcıdır (GTK uygulamalarının kullandığı aynı
döngü); belleğini kilitlemez, bu yüzden bellek baskısında bir masaüstü uygulaması gibi yavaşlar.
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from nefes_olcum import (  # noqa: E402
    PROBE_FILE,
    PSI_FILE,
    Probe,
    psi_row,
    summarize,
    summarize_run,
    write_probe_csv,
    write_psi_csv,
)
from nefesd.psi import parse_pressure  # noqa: E402

PSI_PATH = Path("/proc/pressure/memory")


def record(out: Path, duration_s: float, interval_ms: int) -> int:
    out.mkdir(parents=True, exist_ok=True)
    loop = GLib.MainLoop()
    probe = Probe(interval_s=interval_ms / 1000.0)
    t0 = time.monotonic()
    probe_rows: list[tuple[float, float]] = []
    psi_rows: list[tuple] = []

    def on_tick() -> bool:
        now = time.monotonic()
        probe_rows.append((round(now - t0, 3), round(probe.tick(now), 1)))
        return GLib.SOURCE_CONTINUE

    def on_psi() -> bool:
        try:
            psi_rows.append(psi_row(round(time.monotonic() - t0, 3), parse_pressure(PSI_PATH.read_text())))
        except (OSError, ValueError) as exc:
            print(f"PSI okunamadı: {exc}", file=sys.stderr)
        return GLib.SOURCE_CONTINUE

    def stop() -> bool:
        loop.quit()
        return GLib.SOURCE_REMOVE

    probe.start(time.monotonic())
    GLib.timeout_add(interval_ms, on_tick)
    GLib.timeout_add(1000, on_psi)
    GLib.timeout_add(int(duration_s * 1000), stop)
    GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGTERM, stop)
    GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGINT, stop)
    loop.run()

    write_probe_csv(out / PROBE_FILE, probe_rows)
    write_psi_csv(out / PSI_FILE, psi_rows)
    if probe_rows:
        print(f"{out}: {_line(summarize([lat for _t, lat in probe_rows]), _psi_max(psi_rows))}")
    return 0


def report(directories: list[Path]) -> int:
    print(f"{'ölçüm':<28} {'örnek':>6} {'p99 ms':>8} {'maks ms':>8} {'M2 donma s':>10} {'M1':>5} {'PSI some maks':>13}")
    for directory in directories:
        try:
            result = summarize_run(directory)
        except (OSError, ValueError, KeyError) as exc:
            print(f"{str(directory):<28} okunamadı: {exc}")
            continue
        s = result["prob"]
        print(f"{directory.name:<28} {s.samples:>6} {s.p99_ms:>8.0f} {s.max_ms:>8.0f} "
              f"{s.freeze_total_s:>10.1f} {'✓' if s.meets_m1() else '✗':>5} {result['psi_some_avg10_max']:>13.1f}")
    return 0


def _psi_max(rows: list[tuple]) -> float:
    return max((row[1] for row in rows), default=0.0)


def _line(s, psi_max: float) -> str:
    return (f"{s.samples} örnek, p99 {s.p99_ms:.0f} ms, maks {s.max_ms:.0f} ms, "
            f"M2 donma {s.freeze_total_s:.1f} s, M1 {'✓' if s.meets_m1() else '✗'}, PSI some maks {psi_max:.1f}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="nefes-olcum", description="Nefes ölçüm araçları (M1, M2, PSI)")
    sub = p.add_subparsers(dest="komut", required=True)
    k = sub.add_parser("kaydet", help="gecikme probu + PSI kaydı")
    k.add_argument("--cikti", type=Path, required=True, help="CSV'lerin yazılacağı klasör")
    k.add_argument("--sure", type=float, default=60.0, help="kayıt süresi (s)")
    k.add_argument("--aralik-ms", type=int, default=100, help="prob aralığı (ms)")
    o = sub.add_parser("ozet", help="ölçüm klasörlerinin özeti")
    o.add_argument("klasorler", type=Path, nargs="+")
    args = p.parse_args(argv)
    if args.komut == "kaydet":
        return record(args.cikti, args.sure, args.aralik_ms)
    return report(args.klasorler)


if __name__ == "__main__":
    sys.exit(main())
