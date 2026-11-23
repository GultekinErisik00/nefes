"""nefes-zram — RAM boyutuna göre zram-generator yapılandırması üretir.

Politika (notlar/03 Çekirdek/zram.md, Deney 02 ölçümleri):
  RAM ≤ 2 GB → zram = RAM × 1,0, zstd   (düşük RAM'de sıkıştırma oranı kritik)
  RAM ≤ 4 GB → zram = RAM × 0,75, zstd
  RAM ≤ 8 GB → zram = RAM × 0,5, lz4    (bol RAM'de daha az CPU)
  RAM > 8 GB → zram = min(RAM/2, 8 GB), lz4
Disk swap kaldırılmaz; zram daha yüksek öncelikle (100) önce kullanılır.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

HEADER = "# nefes-zram tarafından üretildi — elle düzenlemeyin"
SWAP_PRIORITY = 100
MAX_ZRAM_MB = 8192


class ForeignConfigError(RuntimeError):
    """Hedef dosya nefes-zram'a ait değil (yöneticinin kendi yapılandırması)."""


def parse_meminfo(text: str) -> int:
    """/proc/meminfo içeriğinden toplam RAM (MB)."""
    for line in text.splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            try:
                kb = int(parts[1])
            except (IndexError, ValueError):
                raise ValueError(f"MemTotal okunamadı: {line!r}") from None
            if kb <= 0:
                raise ValueError(f"MemTotal pozitif değil: {kb}")
            return kb // 1024
    raise ValueError("/proc/meminfo içinde MemTotal yok")


def zram_size_mb(ram_mb: int) -> int:
    _check_ram(ram_mb)
    if ram_mb <= 2048:
        return ram_mb
    if ram_mb <= 4096:
        return ram_mb * 3 // 4
    return min(ram_mb // 2, MAX_ZRAM_MB)


def algorithm_for(ram_mb: int) -> str:
    _check_ram(ram_mb)
    return "zstd" if ram_mb <= 4096 else "lz4"


def render_config(ram_mb: int) -> str:
    return (
        f"{HEADER}\n"
        f"# RAM: {ram_mb} MB\n"
        "[zram0]\n"
        f"zram-size = {zram_size_mb(ram_mb)}\n"
        f"compression-algorithm = {algorithm_for(ram_mb)}\n"
        f"swap-priority = {SWAP_PRIORITY}\n"
    )


def write_config(path: Path, content: str, force: bool = False) -> None:
    """Atomik yazar (geçici dosya + os.replace, 0644). Yöneticinin kendi dosyasını `force` olmadan ezmez."""
    path = Path(path)
    if path.exists() and not force and not _is_ours(path):
        raise ForeignConfigError(f"{path} nefes-zram'a ait değil; üzerine yazmak için --force")
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fchmod(handle.fileno(), 0o644)
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _is_ours(path: Path) -> bool:
    with path.open(encoding="utf-8", errors="replace") as handle:
        return handle.readline().rstrip("\n") == HEADER


def _check_ram(ram_mb: int) -> None:
    if ram_mb <= 0:
        raise ValueError(f"RAM pozitif olmalı: {ram_mb} MB")
