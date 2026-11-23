"""nefes_zram birim testleri — RAM'e göre zram-generator yapılandırması.

Politika (notlar/03 Çekirdek/zram.md, Deney 02): ≤2 GB → RAM×1,0 zstd; ≤4 GB → ×0,75 zstd;
≤8 GB → ×0,5 lz4; >8 GB → en çok 8 GB lz4. Boyutlar MB, tamsayı (aşağı yuvarlanır).
"""
import os

import pytest

from nefes_zram import (
    HEADER,
    ForeignConfigError,
    algorithm_for,
    parse_meminfo,
    render_config,
    write_config,
    zram_size_mb,
)

MEMINFO = "MemTotal:        2021304 kB\nMemFree:          458000 kB\nSwapTotal:       1127420 kB\n"


def test_parse_meminfo_returns_total_ram_in_mb():
    assert parse_meminfo(MEMINFO) == 1973  # 2021304 kB // 1024


@pytest.mark.parametrize("text", ["", "MemFree: 1000 kB\n", "MemTotal: abc kB\n", "MemTotal: 0 kB\n"])
def test_parse_meminfo_rejects_missing_or_invalid_total(text):
    with pytest.raises(ValueError):
        parse_meminfo(text)


@pytest.mark.parametrize(
    "ram_mb, expected",
    [
        (1024, 1024),  # ≤2 GB: ×1,0
        (1973, 1973),
        (2048, 2048),  # sınır: hâlâ ×1,0
        (2049, 1536),  # 2 GB üstü: ×0,75 (2049*0,75=1536,75 → 1536)
        (4096, 3072),  # sınır: ×0,75
        (4097, 2048),  # 4 GB üstü: ×0,5
        (8192, 4096),  # sınır: ×0,5
        (16384, 8192),  # >8 GB: ram/2 ama en çok 8192
        (65536, 8192),
    ],
)
def test_zram_size_follows_ram_tiers(ram_mb, expected):
    assert zram_size_mb(ram_mb) == expected


@pytest.mark.parametrize("ram_mb, expected", [(1973, "zstd"), (4096, "zstd"), (4097, "lz4"), (16384, "lz4")])
def test_algorithm_is_zstd_on_small_machines_and_lz4_on_large(ram_mb, expected):
    assert algorithm_for(ram_mb) == expected


@pytest.mark.parametrize("ram_mb", [0, -1])
def test_non_positive_ram_is_rejected(ram_mb):
    with pytest.raises(ValueError):
        zram_size_mb(ram_mb)


def test_render_config_for_a_2gb_pardus_machine():
    assert render_config(1973) == (
        f"{HEADER}\n"
        "# RAM: 1973 MB\n"
        "[zram0]\n"
        "zram-size = 1973\n"
        "compression-algorithm = zstd\n"
        "swap-priority = 100\n"
    )


# --- yazma ---------------------------------------------------------------------

def test_write_config_creates_file_with_content_and_mode_644(tmp_path):
    target = tmp_path / "zram-generator.conf"
    write_config(target, render_config(1973))
    assert target.read_text() == render_config(1973)
    assert oct(target.stat().st_mode & 0o777) == "0o644"


def test_write_config_replaces_its_own_previous_file(tmp_path):
    target = tmp_path / "zram-generator.conf"
    write_config(target, render_config(1024))
    write_config(target, render_config(1973))
    assert "zram-size = 1973" in target.read_text()


def test_write_config_refuses_to_overwrite_an_admins_own_config(tmp_path):
    target = tmp_path / "zram-generator.conf"
    target.write_text("[zram0]\nzram-size = 512\n")
    with pytest.raises(ForeignConfigError):
        write_config(target, render_config(1973))
    assert target.read_text() == "[zram0]\nzram-size = 512\n"


def test_write_config_force_overwrites_an_admins_config(tmp_path):
    target = tmp_path / "zram-generator.conf"
    target.write_text("[zram0]\nzram-size = 512\n")
    write_config(target, render_config(1973), force=True)
    assert "zram-size = 1973" in target.read_text()


def test_write_config_leaves_no_temporary_files(tmp_path):
    target = tmp_path / "zram-generator.conf"
    write_config(target, render_config(1973))
    assert sorted(os.listdir(tmp_path)) == ["zram-generator.conf"]


# --- komut satırı: python3 -m nefes_zram ------------------------------------------

def test_cli_writes_config_computed_from_meminfo(tmp_path):
    from nefes_zram.__main__ import main

    meminfo = tmp_path / "meminfo"
    meminfo.write_text(MEMINFO)
    out = tmp_path / "zram-generator.conf"
    assert main(["--meminfo", str(meminfo), "--output", str(out)]) == 0
    assert out.read_text() == render_config(1973)


def test_cli_refuses_foreign_config_with_nonzero_exit(tmp_path):
    from nefes_zram.__main__ import main

    meminfo = tmp_path / "meminfo"
    meminfo.write_text(MEMINFO)
    out = tmp_path / "zram-generator.conf"
    out.write_text("[zram0]\nzram-size = 512\n")
    assert main(["--meminfo", str(meminfo), "--output", str(out)]) == 2
    assert out.read_text() == "[zram0]\nzram-size = 512\n"
