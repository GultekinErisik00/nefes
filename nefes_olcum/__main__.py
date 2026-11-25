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
    mean_sd,
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
    print(f"{'ölçüm':<28} {'örnek':>6} {'p99 ms':>8} {'maks ms':>8} {'M2 donma s':>10} {'M1':>5} "
          f"{'M3 ölen':>8} {'PSI some maks':>13}")
    groups: dict[str, list[dict]] = {}
    for directory in directories:
        try:
            result = summarize_run(directory)
        except (OSError, ValueError, KeyError) as exc:
            print(f"{str(directory):<28} okunamadı: {exc}")
            continue
        s = result["prob"]
        killed = "-" if result["killed_apps"] is None else str(result["killed_apps"])
        print(f"{directory.name:<28} {s.samples:>6} {s.p99_ms:>8.0f} {s.max_ms:>8.0f} "
              f"{s.freeze_total_s:>10.1f} {'✓' if s.meets_m1() else '✗':>5} {killed:>8} "
              f"{result['psi_some_avg10_max']:>13.1f}")
        groups.setdefault(directory.name.rstrip("/").rsplit("-", 1)[0], []).append(result)
    if any(len(runs) > 1 for runs in groups.values()):
        print(f"\n{'yapılandırma (ort. ± sapma)':<28} {'n':>3} {'p99 ms':>14} {'maks ms':>16} "
              f"{'M2 donma s':>14} {'M3 ölen':>12} {'PSI some maks':>14}")
        for name, runs in groups.items():
            def stat(values, fmt):
                mean, sd = mean_sd(values)
                return f"{mean:{fmt}} ± {sd:{fmt}}"
            killed = [r["killed_apps"] for r in runs if r["killed_apps"] is not None]
            print(f"{name:<28} {len(runs):>3} "
                  f"{stat([r['prob'].p99_ms for r in runs], '.0f'):>14} "
                  f"{stat([r['prob'].max_ms for r in runs], '.0f'):>16} "
                  f"{stat([r['prob'].freeze_total_s for r in runs], '.1f'):>14} "
                  f"{stat(killed, '.1f') if killed else '-':>12} "
                  f"{stat([r['psi_some_avg10_max'] for r in runs], '.1f'):>14}")
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
