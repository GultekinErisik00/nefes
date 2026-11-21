"""cgroup v2 dosya sistemi sınırı — nefesd'nin /sys/fs/cgroup'a dokunan tek modülü.

Okuma: kullanıcının app.slice'ı altındaki scope'lar ve bellek kullanımları.
Yazma: cgroup.freeze ve memory.reclaim — yalnızca `karar.app_scope_parts` ile geçerli sayılan
yollara. Yazma yolu kökten başlayıp her klasörü `O_NOFOLLOW` ile tek tek açar (dir_fd), böylece
kontrol ile yazma arasında sembolik bağ araya giremez. Uygulama kapanmışsa `ScopeGone` yükselir.
"""
from __future__ import annotations

import errno
import os
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from nefesd.karar import AppCgroup, app_scope_parts

_GONE = frozenset({errno.ENOENT, errno.ENODEV, errno.ESRCH})
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


class CgroupPathError(ValueError):
    """Yol, bu kullanıcının bir uygulama scope'u değil; yazma reddedildi."""


class ScopeGone(Exception):
    """Scope artık yok (uygulama kapandı) — daemon için olağan durum, hata değil."""


@dataclass(frozen=True)
class ReclaimResult:
    requested: int
    before: int  # bayt, yazmadan önce memory.current
    after: int  # bayt, yazmadan sonra memory.current
    complete: bool  # False = çekirdek istenen miktarı alamadı (EAGAIN) — hata değil


def read_apps(root: Path, uid: int, frozen_since: Mapping[str, float]) -> tuple[AppCgroup, ...]:
    """app.slice altındaki uygulama scope'larını bellek kullanımlarıyla döndürür (yola göre sıralı)."""
    apps = []
    for path, directory in _app_scopes(root, uid):
        try:
            memory = int((directory / "memory.current").read_text())
        except (OSError, ValueError):
            continue  # tarama sırasında scope bitti
        apps.append(AppCgroup(path, memory, frozen_since.get(path)))
    return tuple(apps)


def list_frozen(root: Path, uid: int) -> tuple[str, ...]:
    """Diskte donmuş görünen scope'lar — servis yeniden başlarken çözülmeleri için."""
    return tuple(path for path, directory in _app_scopes(root, uid) if _is_frozen(directory))


def cgroup_of_pid(pid: int, proc_root: Path = Path("/proc")) -> str | None:
    """/proc/<pid>/cgroup içindeki cgroup v2 ("0::") yolu; süreç yoksa None."""
    try:
        lines = (proc_root / str(pid) / "cgroup").read_text().splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("0::"):
            return line[3:]
    return None


def freeze(root: Path, path: str, uid: int) -> None:
    _set_freeze(root, path, uid, "1")


def thaw(root: Path, path: str, uid: int) -> None:
    _set_freeze(root, path, uid, "0")


def reclaim(root: Path, path: str, uid: int, nbytes: int) -> ReclaimResult:
    """memory.reclaim'e nbytes yazar. Çekirdek tamamını alamazsa EAGAIN → complete=False."""
    if nbytes <= 0:
        raise ValueError(f"geri kazanılacak miktar pozitif olmalı: {nbytes}")
    dirfd = _open_scope_dir(root, path, uid)
    try:
        before = _read_int_at(dirfd, "memory.current", path)
        complete = True
        try:
            _write_at(dirfd, "memory.reclaim", str(nbytes), path)
        except OSError as exc:
            if exc.errno != errno.EAGAIN:
                raise
            complete = False
        after = _read_int_at(dirfd, "memory.current", path)
    finally:
        os.close(dirfd)
    return ReclaimResult(nbytes, before, after, complete)


# --- yazma yolu: dir_fd ile, sembolik bağ izlemeden ------------------------------------------

def _set_freeze(root: Path, path: str, uid: int, value: str) -> None:
    dirfd = _open_scope_dir(root, path, uid)
    try:
        _write_at(dirfd, "cgroup.freeze", value, path)
    finally:
        os.close(dirfd)


def _open_scope_dir(root: Path, path: str, uid: int) -> int:
    """Kökten başlayarak doğrulanmış yolun her parçasını O_NOFOLLOW ile açar; scope'un fd'si."""
    parts = app_scope_parts(path, uid)
    if parts is None:
        raise CgroupPathError(f"uygulama scope'u değil: {path!r}")
    chain = ("user.slice", f"user-{uid}.slice", f"user@{uid}.service", "app.slice", *parts)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in chain:
            try:
                next_fd = os.open(part, _DIR_FLAGS, dir_fd=fd)
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                    raise CgroupPathError(f"yol sembolik bağ ya da klasör değil: {path!r}") from exc
                if exc.errno in _GONE:
                    raise ScopeGone(path) from exc
                raise
            os.close(fd)
            fd = next_fd
    except BaseException:
        os.close(fd)
        raise
    return fd


def _write_at(dirfd: int, name: str, value: str, path: str) -> None:
    # O_CREAT yok: arayüz dosyası yoksa yeni dosya yaratılmaz (scope kapanmış demektir).
    try:
        fd = os.open(name, os.O_WRONLY | os.O_NOFOLLOW, dir_fd=dirfd)
    except OSError as exc:
        if exc.errno in _GONE:
            raise ScopeGone(path) from exc
        raise
    try:
        data = value.encode()
        if os.write(fd, data) != len(data):
            raise OSError(errno.EIO, f"{name}: kısa yazma")
    except OSError as exc:
        if exc.errno in _GONE:
            raise ScopeGone(path) from exc
        raise
    finally:
        os.close(fd)


def _read_int_at(dirfd: int, name: str, path: str) -> int:
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dirfd)
        try:
            text = os.read(fd, 64).decode()
        finally:
            os.close(fd)
    except OSError as exc:
        if exc.errno in _GONE:
            raise ScopeGone(path) from exc
        raise
    try:
        return int(text)
    except ValueError:
        raise ValueError(f"{path}/{name}: sayı değil: {text.strip()!r}") from None


# --- okuma yolu: tarama ---------------------------------------------------------------------

def _app_slice_dir(root: Path, uid: int) -> Path:
    return root / "user.slice" / f"user-{uid}.slice" / f"user@{uid}.service" / "app.slice"


def _app_scopes(root: Path, uid: int) -> Iterator[tuple[str, Path]]:
    """app.slice altında *.slice klasörlerine inerek *.scope'ları bulur; bağları izlemez."""
    base = _app_slice_dir(root, uid)
    if base.is_symlink() or not base.is_dir():
        return
    found, pending = [], [base]
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            continue  # tarama sırasında silindi
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            child = Path(entry.path)
            if entry.name.endswith(".slice"):
                pending.append(child)
            elif entry.name.endswith(".scope"):
                path = "/" + child.relative_to(root).as_posix()
                if app_scope_parts(path, uid) is not None:
                    found.append((path, child))
    yield from sorted(found)


def _is_frozen(directory: Path) -> bool:
    try:
        lines = (directory / "cgroup.events").read_text().splitlines()
    except OSError:
        return False
    return "frozen 1" in lines
