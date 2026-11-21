"""Nefes karar motoru — saf fonksiyon, dosya sistemine dokunmaz.

Girdi: o anki cgroup anlık görüntüsü + politika. Çıktı: uygulanacak eylemler (sırasıyla).
Güvenlik kuralları (M6): odaktaki uygulama, korunan adlar ve kullanıcının kendi
app.slice'ı dışındaki her şey asla dondurulmaz; odak bilinmiyorsa hiçbir şey dondurulmaz;
hiçbir uygulama `max_frozen_seconds`'tan uzun donuk kalmaz.

Eşit bellekte ilk gelen aday seçilir. `now` ve `frozen_since` monoton saatten gelmelidir.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Pressure(Enum):
    NORMAL = "normal"
    HIGH = "high"
    SAFE = "safe"


@dataclass(frozen=True)
class AppCgroup:
    path: str  # /proc/<pid>/cgroup biçimi: cgroup köküne göre, "/" ile başlar
    memory_current: int
    frozen_since: float | None = None


@dataclass(frozen=True)
class Policy:
    uid: int  # yalnızca bu kullanıcının uygulamaları aday olur
    protected_names: frozenset[str]
    max_frozen_seconds: float
    min_candidate_bytes: int


@dataclass(frozen=True)
class Snapshot:
    apps: tuple[AppCgroup, ...]
    focus_path: str | None  # odaktaki pencerenin cgroup'u; None = odakta pencere yok
    focus_known: bool  # False = odak okunamadı → güvenli taraf: dondurma yok
    pressure: Pressure
    now: float


@dataclass(frozen=True)
class Freeze:
    path: str


@dataclass(frozen=True)
class Thaw:
    path: str
    reason: str  # "focus" | "timeout" | "pressure_low"


Action = Freeze | Thaw


def decide(snapshot: Snapshot, policy: Policy) -> tuple[Action, ...]:
    """Bir tur için eylemleri döndürür: önce zorunlu çözmeler, sonra baskı eylemi."""
    apps = _unique_by_path(snapshot.apps)
    thaws = _forced_thaws(apps, snapshot, policy)
    thawed = {t.path for t in thaws}

    if snapshot.pressure is Pressure.HIGH:
        candidate = _pick_candidate(apps, snapshot, policy)
        return thaws + ((Freeze(candidate.path),) if candidate else ())

    if snapshot.pressure is Pressure.SAFE:
        still_frozen = [
            (a.frozen_since, a) for a in apps if a.frozen_since is not None and a.path not in thawed
        ]
        if still_frozen:
            _, oldest = min(still_frozen, key=lambda pair: pair[0])
            return thaws + (Thaw(oldest.path, "pressure_low"),)

    return thaws


def _unique_by_path(apps: tuple[AppCgroup, ...]) -> tuple[AppCgroup, ...]:
    first: dict[str, AppCgroup] = {}
    for app in apps:
        first.setdefault(app.path, app)
    return tuple(first.values())


def _forced_thaws(
    apps: tuple[AppCgroup, ...], snapshot: Snapshot, policy: Policy
) -> tuple[Thaw, ...]:
    thaws = []
    for app in apps:
        if app.frozen_since is None:
            continue
        if _is_focused(app, snapshot.focus_path):
            thaws.append(Thaw(app.path, "focus"))
        elif snapshot.now - app.frozen_since > policy.max_frozen_seconds:
            thaws.append(Thaw(app.path, "timeout"))
    return tuple(thaws)


def _pick_candidate(
    apps: tuple[AppCgroup, ...], snapshot: Snapshot, policy: Policy
) -> AppCgroup | None:
    if not snapshot.focus_known:
        return None
    candidates = [
        app
        for app in apps
        if app.frozen_since is None
        and app.memory_current >= policy.min_candidate_bytes
        and not _is_focused(app, snapshot.focus_path)
        and _is_unprotected_app_scope(app.path, policy)
    ]
    return max(candidates, key=lambda a: a.memory_current, default=None)


def _is_focused(app: AppCgroup, focus_path: str | None) -> bool:
    if focus_path is None:
        return False
    return focus_path == app.path or focus_path.startswith(app.path + "/")


def app_scope_parts(path: str, uid: int) -> tuple[str, ...] | None:
    """app.slice altındaki yol parçaları; yol geçerli bir uygulama scope'u değilse None.

    Geçerli: /user.slice/user-UID.slice/user@UID.service/app.slice/[*.slice/]*NAME.scope
    Reddedilen: başka uid, '.', '..', boş parça, yazdırılamaz karakter, scope içinde scope.
    """
    prefix = f"/user.slice/user-{uid}.slice/user@{uid}.service/app.slice/"
    if not path.startswith(prefix):
        return None
    parts = tuple(path[len(prefix):].split("/"))
    if any(p in ("", ".", "..") or not p.isprintable() for p in parts):
        return None
    *slices, unit = parts
    if not unit.endswith(".scope") or not all(s.endswith(".slice") for s in slices):
        return None
    return parts


def _is_unprotected_app_scope(path: str, policy: Policy) -> bool:
    parts = app_scope_parts(path, policy.uid)
    if parts is None:
        return False
    return not any(name in part for part in parts for name in policy.protected_names)
