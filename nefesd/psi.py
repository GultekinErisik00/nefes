"""PSI (Pressure Stall Information) — /proc/pressure/memory okuma ve tetikleyici satırı.

Tetikleyici biçimi (docs.kernel.org/accounting/psi.html): "<some|full> <stall_us> <window_us>",
pencere 500 ms – 10 s, stall pencereden büyük olamaz.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from nefesd.karar import Pressure

MIN_WINDOW_US = 500_000
MAX_WINDOW_US = 10_000_000


@dataclass(frozen=True)
class PressureStats:
    some_avg10: float
    some_avg60: float
    some_total: int
    full_avg10: float
    full_avg60: float
    full_total: int


def parse_pressure(text: str) -> PressureStats:
    """/proc/pressure/memory içeriğini ayrıştırır; bozuk girdide anlamlı bir ValueError verir."""
    lines: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        kind, _, rest = line.partition(" ")
        if kind not in ("some", "full"):
            continue
        try:
            lines[kind] = dict(field.split("=", 1) for field in rest.split())
        except ValueError:
            raise ValueError(f"PSI satırı bozuk: {line!r}") from None
    if "some" not in lines:
        raise ValueError("PSI çıktısında 'some' satırı yok")
    some = lines["some"]
    full = lines.get("full", {"avg10": "0", "avg60": "0", "total": "0"})
    return PressureStats(
        some_avg10=_number(some, "avg10", "some"),
        some_avg60=_number(some, "avg60", "some"),
        some_total=int(_number(some, "total", "some")),
        full_avg10=_number(full, "avg10", "full"),
        full_avg60=_number(full, "avg60", "full"),
        full_total=int(_number(full, "total", "full")),
    )


def _number(fields: dict[str, str], key: str, kind: str) -> float:
    try:
        value = float(fields[key])
    except (KeyError, ValueError):
        raise ValueError(f"PSI '{kind}' satırında geçersiz ya da eksik '{key}'") from None
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"PSI '{kind}' satırında geçersiz '{key}': {value}")
    return value


def trigger_line(kind: str, stall_us: int, window_us: int) -> bytes:
    """Çekirdeğe yazılacak tetikleyici satırı; çekirdeğin reddedeceği değerlerde ValueError."""
    if type(stall_us) is not int or type(window_us) is not int:
        raise ValueError("stall ve pencere tamsayı (µs) olmalı")
    if kind not in ("some", "full"):
        raise ValueError(f"tür 'some' ya da 'full' olmalı: {kind!r}")
    if not MIN_WINDOW_US <= window_us <= MAX_WINDOW_US:
        raise ValueError(f"pencere 500 ms – 10 s aralığında olmalı: {window_us} µs")
    if not 0 < stall_us <= window_us:
        raise ValueError(f"stall 0'dan büyük ve pencereden küçük/eşit olmalı: {stall_us} µs")
    return f"{kind} {stall_us} {window_us}\0".encode()


def classify(fired: bool, some_avg10: float, safe_below: float) -> Pressure:
    """Tetikleyici geldiyse HIGH; sessizken some avg10 eşiğin altındaysa SAFE, değilse NORMAL."""
    if fired:
        return Pressure.HIGH
    return Pressure.SAFE if some_avg10 < safe_below else Pressure.NORMAL
