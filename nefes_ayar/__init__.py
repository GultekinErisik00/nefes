"""nefes_ayar — kullanıcı ayar dosyası (~/.config/nefes/ayarlar.ini), arayüz tasarımı 2026-11-25.

Dosyaya yalnızca nefes-agent yazar (tek yazar → kayıp güncelleme yok); nefesd yalnızca okur.
Bozuk bir alan yalnızca o alanı varsayılana döndürür; okunamayan dosya tüm varsayılanları verir.
Hiçbir ayar hatası istisna fırlatmaz: servis ayar yüzünden düşmemeli.
"""
from __future__ import annotations

import configparser
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

SECTION = "nefes"
SENSITIVITY_STALL_MS: dict[str, int] = {"az": 500, "orta": 300, "cok": 200}
MAX_FROZEN_CHOICES_MIN: tuple[int, ...] = (5, 10, 20, 30)
RESERVED_NEVER_FREEZE: frozenset[str] = frozenset({"app", "nefes", "scope", "slice", "service"})
MIN_NEVER_FREEZE_LEN = 3
_TRUE = {"true", "evet", "1", "yes", "on"}
_FALSE = {"false", "hayır", "hayir", "0", "no", "off"}


@dataclass(frozen=True)
class Settings:
    enabled: bool = True
    sensitivity: str = "orta"
    max_frozen_min: int = 10
    never_freeze: tuple[str, ...] = ()
    notifications: bool = True

    @property
    def stall_ms(self) -> int:
        return SENSITIVITY_STALL_MS[self.sensitivity]

    @property
    def max_frozen_seconds(self) -> float:
        return float(self.max_frozen_min * 60)


def config_path(env: Mapping[str, str] = os.environ) -> Path:
    base = env.get("XDG_CONFIG_HOME") or str(Path(env.get("HOME", "~")) / ".config")
    return Path(base) / "nefes" / "ayarlar.ini"


def normalize_name(name: str) -> str:
    """nefes_baslat.unit_name ile aynı kural: scope adındaki program adıyla eşleşsin."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def is_valid_never_freeze(name: str) -> bool:
    """Genel scope sözcükleri (app, nefes, scope…) ya da 3 karakterden kısa adlar tüm sistemi koruyup
    Nefes'i etkisizleştirebilir → reddedilir."""
    return (
        len(name) >= MIN_NEVER_FREEZE_LEN
        and name not in RESERVED_NEVER_FREEZE
        and not name.startswith("app-nefes")
    )


def validate(settings: Settings) -> str | None:
    if settings.sensitivity not in SENSITIVITY_STALL_MS:
        return f"hassasiyet geçersiz: {settings.sensitivity!r} (az, orta ya da cok olmalı)"
    if settings.max_frozen_min not in MAX_FROZEN_CHOICES_MIN:
        return f"en uzun donma geçersiz: {settings.max_frozen_min} dk (5, 10, 20 ya da 30 olmalı)"
    for name in settings.never_freeze:
        if not name:
            return "asla dondurma listesinde boş ad var"
        if not is_valid_never_freeze(name):
            return f"asla dondurma geçersiz ({name!r}): çok genel veya kısa"
    return None


def load(path: Path) -> tuple[Settings, tuple[str, ...]]:
    """(ayarlar, Türkçe uyarılar). Dosya yoksa varsayılanlar, uyarısız."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return Settings(), ()
    except (OSError, UnicodeDecodeError) as exc:
        return Settings(), (f"ayar dosyası okunamadı, varsayılanlar kullanılıyor: {exc}",)
    parser = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";", "#"))
    try:
        parser.read_string(text)
    except configparser.Error as exc:
        return Settings(), (f"ayar dosyası bozuk, varsayılanlar kullanılıyor: {exc}",)
    if not parser.has_section(SECTION):
        return Settings(), ()
    return _parse(parser[SECTION])


def _parse(section: configparser.SectionProxy) -> tuple[Settings, tuple[str, ...]]:
    default = Settings()
    warnings: list[str] = []

    def boolean(key: str, fallback: bool) -> bool:
        raw = section.get(key)
        if raw is None:
            return fallback
        value = raw.strip().lower()
        if value in _TRUE:
            return True
        if value in _FALSE:
            return False
        warnings.append(f"{key} geçersiz ({raw!r}), varsayılan kullanılıyor")
        return fallback

    sensitivity = section.get("hassasiyet", default.sensitivity).strip().lower()
    if sensitivity not in SENSITIVITY_STALL_MS:
        warnings.append(f"hassasiyet geçersiz ({sensitivity!r}), varsayılan kullanılıyor")
        sensitivity = default.sensitivity

    raw_minutes = section.get("en_uzun_donma_dk", str(default.max_frozen_min)).strip()
    minutes = int(raw_minutes) if (raw_minutes.isascii() and raw_minutes.isdigit()) else -1
    if minutes not in MAX_FROZEN_CHOICES_MIN:
        warnings.append(f"en_uzun_donma_dk geçersiz ({raw_minutes!r}), varsayılan kullanılıyor")
        minutes = default.max_frozen_min

    names: list[str] = []
    for item in section.get("asla_dondurma", "").split(","):
        name = normalize_name(item)
        if not name:  # boş ad her scope'la eşleşip Nefes'i kapatırdı → atılır
            continue
        if not is_valid_never_freeze(name):
            warnings.append(f"asla_dondurma geçersiz ({name!r}): çok genel veya kısa, yok sayıldı")
            continue
        if name not in names:
            names.append(name)

    settings = Settings(
        enabled=boolean("etkin", default.enabled),
        sensitivity=sensitivity,
        max_frozen_min=minutes,
        never_freeze=tuple(names),
        notifications=boolean("bildirim", default.notifications),
    )
    return settings, tuple(warnings)


def save(path: Path, settings: Settings) -> None:
    """Atomik yazma: aynı dizinde geçici dosya + os.replace (yarım dosya okunmaz)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        f"[{SECTION}]\n"
        f"etkin = {'true' if settings.enabled else 'false'}\n"
        f"hassasiyet = {settings.sensitivity}\n"
        f"en_uzun_donma_dk = {settings.max_frozen_min}\n"
        f"asla_dondurma = {', '.join(settings.never_freeze)}\n"
        f"bildirim = {'true' if settings.notifications else 'false'}\n"
    )
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".ayarlar-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def update(path: Path, **changes) -> tuple[Settings, Settings]:
    """Dosyayı taze okuyup yalnızca verilen alanları atomik olarak günceller; (eski, yeni) döner."""
    current, _warnings = load(path)
    updated = replace(current, **changes)
    if updated != current:
        save(path, updated)
    return current, updated
