"""RAM ve zram kullanımı — /proc/meminfo ve /sys/block/zram0/mm_stat (root gerekmez)."""
from __future__ import annotations

from pathlib import Path


def parse_meminfo(text: str) -> tuple[int, int]:
    """(kullanılan, toplam) bayt; kullanılan = MemTotal − MemAvailable."""
    fields = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            fields[key.strip()] = int(parts[0]) * 1024
    total = fields.get("MemTotal", 0)
    return total - fields.get("MemAvailable", total), total


def parse_mm_stat(text: str) -> tuple[int, int] | None:
    """(sıkıştırılmadan önceki veri, zram'ın kullandığı bellek) bayt; bozuksa None."""
    parts = text.split()
    if len(parts) < 3 or not (parts[0].isdigit() and parts[2].isdigit()):
        return None
    return int(parts[0]), int(parts[2])


def read_memory(proc: Path = Path("/proc"), sys: Path = Path("/sys")
                ) -> tuple[tuple[int, int], tuple[int, int] | None]:
    ram = parse_meminfo((proc / "meminfo").read_text())
    try:
        zram = parse_mm_stat((sys / "block" / "zram0" / "mm_stat").read_text())
    except OSError:
        zram = None
    return ram, zram
