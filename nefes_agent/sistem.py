"""RAM, zram ve app.slice açık uygulamaları — /proc ve /sys (root gerekmez)."""
from __future__ import annotations

import os
import re
from pathlib import Path

_LAUNCHER_PREFIXES = ("nefes-", "gnome-", "xfce-")
_INSTANCE_SUFFIX = re.compile(r"-(?:\d+|[0-9a-f]{8})$")


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


def scope_app_name(unit: str) -> str:
    """Scope birim adından kullanıcıya gösterilecek kısa uygulama adı."""
    base = unit.rstrip("/").rsplit("/", 1)[-1].removesuffix(".scope")
    name = base.removeprefix("app-")
    for prefix in _LAUNCHER_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    name = _INSTANCE_SUFFIX.sub("", name)
    return name or base


def read_running_apps(
    cgroup_root: Path = Path("/sys/fs/cgroup"),
    uid: int | None = None,
) -> list[tuple[str, str, int, bool]]:
    """Kullanıcının app.slice altındaki uygulama scope'ları: (yol, ad, bellek_bayt, donuk_mu).

    Bellek kullanımına göre büyükten küçüğe sıralıdır; sembolik bağları izlemez.
    """
    uid = os.getuid() if uid is None else uid
    base = cgroup_root / "user.slice" / f"user-{uid}.slice" / f"user@{uid}.service" / "app.slice"
    if base.is_symlink() or not base.is_dir():
        return []
    apps: list[tuple[str, str, int, bool]] = []
    pending = [base]
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            child = Path(entry.path)
            if entry.name.endswith(".slice"):
                pending.append(child)
            elif entry.name.endswith(".scope"):
                try:
                    memory = int((child / "memory.current").read_text().strip())
                except (OSError, ValueError):
                    continue
                try:
                    frozen = "frozen 1" in (child / "cgroup.events").read_text().splitlines()
                except OSError:
                    frozen = False
                rel = "/" + child.relative_to(cgroup_root).as_posix()
                apps.append((rel, scope_app_name(entry.name), memory, frozen))
    apps.sort(key=lambda item: (-item[2], item[1], item[0]))
    return apps
