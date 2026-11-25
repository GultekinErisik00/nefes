"""Simge durumu ve pencere metinleri — saf işlevler (arayüz tasarımı, 2026-11-25).

GTK'ya dokunmaz; nefes_agent.simge ve nefes_agent.pencere bu metinleri olduğu gibi gösterir.
"""
from __future__ import annotations

import shlex
from collections.abc import Sequence
from datetime import datetime, tzinfo
from pathlib import Path

from nefes_agent import display_name

MB = 1024 * 1024
LEVEL_TEXT = {"safe": "düşük", "normal": "orta", "high": "yüksek"}
REASON_TEXT = {
    "pressure": "baskı yüksek", "user": "sen", "focus": "odaklandın", "timeout": "süre doldu",
    "pressure_low": "baskı azaldı", "paused": "duraklatıldı", "shutdown": "Nefes kapandı",
}
_BARS = "▁▂▃▄▅▆▇█"


def tray_state(service_up: bool, enabled: bool, level: str, frozen_count: int) -> tuple[str, str]:
    """(simge adı, ipucu). Öncelik: çalışmıyor > duraklatıldı > donuk > baskı yüksek > normal."""
    if not service_up:
        return "nefes-kapali", "Nefes çalışmıyor"
    if not enabled:
        return "nefes-duraklatildi", "Nefes duraklatıldı"
    if frozen_count > 0:
        return "nefes-donuk", f"Nefes açık — {frozen_count} uygulama donduruldu"
    text = f"Nefes açık — baskı {LEVEL_TEXT.get(level, level)}"
    return ("nefes-baski" if level == "high" else "nefes-normal"), text


def format_mb(nbytes: int) -> str:
    mb = nbytes // MB
    if mb < 1024:
        return f"{mb} MB"
    return f"{nbytes / (1024 * MB):.1f} GB".replace(".", ",")


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} sn"
    if seconds < 3600:
        return f"{seconds // 60} dk"
    hours, minutes = divmod(seconds // 60, 60)
    return f"{hours} sa" + (f" {minutes} dk" if minutes else "")


def event_line(when: int, kind: str, app_name: str, reason: str, tz: tzinfo | None = None) -> str:
    clock = datetime.fromtimestamp(when, tz).strftime("%H:%M")
    verb = "donduruldu" if kind == "frozen" else "devam ettirildi"
    return f"{clock} {display_name(app_name)} {verb} ({REASON_TEXT.get(reason, 'çözüldü')})"


def sparkline(values: Sequence[float], width: int = 60) -> str:
    """Son `width` değer, 0–100 ölçeğinde (PSI some avg10 yüzdedir)."""
    out = []
    for value in list(values)[-width:]:
        clipped = min(100.0, max(0.0, float(value)))
        out.append(_BARS[round(clipped / 100 * (len(_BARS) - 1))])
    return "".join(out)


def app_choice(desktop_text: str) -> tuple[str, str] | None:
    """Menü kaydından ("Name", scope adındaki program adı). nefes-baslat sarmalayıcısı ve
    `env VAR=…` atlanır; ad, nefes_baslat.unit_name ile aynı kuralla normalleştirilir."""
    from nefes_ayar import normalize_name

    fields: dict[str, str] = {}
    in_entry = False
    for line in desktop_text.splitlines():
        if line.startswith("["):
            in_entry = line.strip() == "[Desktop Entry]"
        elif in_entry and "=" in line:
            key, value = line.split("=", 1)
            fields.setdefault(key.strip(), value.strip())
    try:
        argv = shlex.split(fields.get("Exec", ""))
    except ValueError:
        return None
    if argv and Path(argv[0]).name == "nefes-baslat":
        argv = argv[1:]
    if argv and Path(argv[0]).name == "env":
        argv = argv[1:]
        while argv and ("=" in argv[0] or argv[0].startswith("-")):
            argv = argv[1:]
    if not argv:
        return None
    program = normalize_name(Path(argv[0]).name)
    return (fields.get("Name") or program, program) if program else None
