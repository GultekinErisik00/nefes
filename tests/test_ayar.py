"""nefes_ayar birim testleri — ~/.config/nefes/ayarlar.ini (arayüz tasarımı, 2026-11-25)."""
from pathlib import Path

import pytest

from nefes_ayar import (
    Settings,
    config_path,
    load,
    normalize_name,
    save,
    update,
    validate,
)


def write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "ayarlar.ini"
    path.write_text("[nefes]\n" + body, encoding="utf-8")
    return path


def test_missing_file_gives_defaults(tmp_path):
    assert load(tmp_path / "yok.ini") == (Settings(), ())


def test_roundtrip(tmp_path):
    settings = Settings(False, "cok", 20, ("vlc", "thunderbird"), False)
    path = tmp_path / "nefes" / "ayarlar.ini"
    save(path, settings)
    assert load(path) == (settings, ())


def test_sensitivity_maps_to_stall_ms():
    assert Settings(sensitivity="az").stall_ms == 500
    assert Settings(sensitivity="orta").stall_ms == 300
    assert Settings(sensitivity="cok").stall_ms == 200
    assert Settings().max_frozen_seconds == 600.0


@pytest.mark.parametrize("line, field, default", [
    ("hassasiyet = cokcok", "sensitivity", "orta"),
    ("en_uzun_donma_dk = abc", "max_frozen_min", 10),
    ("en_uzun_donma_dk = 7", "max_frozen_min", 10),
    ("en_uzun_donma_dk = ²", "max_frozen_min", 10),  # Unicode üst simge: isdigit True ama int() ValueError
    ("en_uzun_donma_dk = ٣", "max_frozen_min", 10),  # ASCII olmayan rakam
    ("etkin = belki", "enabled", True),
])
def test_bad_field_falls_back_per_field(tmp_path, line, field, default):
    path = write(tmp_path, f"bildirim = false\nasla_dondurma = vlc\n{line}\n")
    settings, warnings = load(path)
    assert getattr(settings, field) == default
    assert settings.notifications is False and settings.never_freeze == ("vlc",)
    assert len(warnings) == 1


def test_unknown_keys_and_sections_are_ignored(tmp_path):
    path = write(tmp_path, "renk = mavi\n[baska]\netkin = false\n")
    assert load(path) == (Settings(), ())


def test_unreadable_file_gives_defaults_with_warning(tmp_path):
    path = tmp_path / "ayarlar.ini"
    path.write_bytes(b"\xff\xfe\x00[")
    settings, warnings = load(path)
    assert settings == Settings()
    assert len(warnings) == 1


def test_never_freeze_is_normalized_and_drops_empty(tmp_path):
    path = write(tmp_path, "asla_dondurma = VLC, , !, Mozilla Thunderbird,vlc\n")
    assert load(path)[0].never_freeze == ("vlc", "mozilla-thunderbird")


def test_normalize_name_follows_unit_name_rule():
    assert normalize_name("Mozilla Thunderbird") == "mozilla-thunderbird"
    assert normalize_name(" !! ") == ""


def test_save_is_atomic_and_leaves_no_temp_files(tmp_path):
    save(tmp_path / "ayarlar.ini", Settings())
    save(tmp_path / "ayarlar.ini", Settings(enabled=False))
    assert [p.name for p in tmp_path.iterdir()] == ["ayarlar.ini"]


def test_config_path_honours_xdg():
    assert config_path({"XDG_CONFIG_HOME": "/x", "HOME": "/h"}) == Path("/x/nefes/ayarlar.ini")
    assert config_path({"HOME": "/h"}) == Path("/h/.config/nefes/ayarlar.ini")


def test_validate_rejects_unknown_choices():
    assert isinstance(validate(Settings(sensitivity="x")), str)
    assert isinstance(validate(Settings(max_frozen_min=7)), str)
    assert isinstance(validate(Settings(never_freeze=("nefes",))), str)
    assert isinstance(validate(Settings(never_freeze=("sh",))), str)
    assert isinstance(validate(Settings(never_freeze=("app-nefes",))), str)
    assert validate(Settings(never_freeze=("vlc",))) is None
    assert validate(Settings()) is None


def test_never_freeze_rejects_reserved_and_short_names_with_warning(tmp_path):
    path = write(tmp_path, "asla_dondurma = app, nefes, scope, slice, service, app-nefes, a, sh, vlc\n")
    settings, warnings = load(path)
    assert settings.never_freeze == ("vlc",)
    assert len(warnings) == 8
    assert all("asla_dondurma" in w for w in warnings)


def test_update_preserves_external_enabled_change(tmp_path):
    """I1: simge/pencere duraklatınca (etkin=false) sonraki ayar değişikliği etkin=true'ya döndürmemeli."""
    path = tmp_path / "ayarlar.ini"
    save(path, Settings(enabled=True, sensitivity="orta"))
    save(path, Settings(enabled=False, sensitivity="orta"))  # set_enabled(False) sonrası dosya
    old, new = update(path, sensitivity="cok")
    assert old.enabled is False and new.enabled is False
    assert new.sensitivity == "cok"
    assert load(path) == (Settings(enabled=False, sensitivity="cok"), ())
