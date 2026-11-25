"""nefes_agent.sistem — /proc/meminfo, zram mm_stat ve app.slice okuma (root gerekmez)."""
from nefes_agent.sistem import (
    parse_meminfo,
    parse_mm_stat,
    read_memory,
    read_running_apps,
    scope_app_name,
)

MEMINFO = """MemTotal:        2013504 kB
MemFree:          120000 kB
MemAvailable:     600000 kB
Buffers:           10000 kB
"""


def test_parse_meminfo_reports_used_and_total_bytes():
    assert parse_meminfo(MEMINFO) == ((2013504 - 600000) * 1024, 2013504 * 1024)


def test_parse_mm_stat_reports_original_and_used():
    assert parse_mm_stat("325058560 99614720 104857600 0 104857600 0 0 0 0") == (325058560, 104857600)


def test_parse_mm_stat_rejects_garbage():
    assert parse_mm_stat("") is None
    assert parse_mm_stat("abc def") is None


def test_read_memory_without_zram(tmp_path):
    (tmp_path / "proc").mkdir()
    (tmp_path / "proc" / "meminfo").write_text(MEMINFO)
    ram, zram = read_memory(proc=tmp_path / "proc", sys=tmp_path / "sys")
    assert ram[1] == 2013504 * 1024 and zram is None


def test_read_memory_with_zram(tmp_path):
    (tmp_path / "proc").mkdir()
    (tmp_path / "proc" / "meminfo").write_text(MEMINFO)
    stat = tmp_path / "sys" / "block" / "zram0"
    stat.mkdir(parents=True)
    (stat / "mm_stat").write_text("1000 500 600 0 600 0 0 0 0\n")
    assert read_memory(proc=tmp_path / "proc", sys=tmp_path / "sys")[1] == (1000, 600)


def test_scope_app_name_extracts_clean_name():
    assert scope_app_name("app-nefes-firefox-esr-a1b2c3d4.scope") == "firefox-esr"
    assert scope_app_name("app-gnome-gimp-1234.scope") == "gimp"
    assert scope_app_name("app-nefes-vlc-deadbeef.scope") == "vlc"


def test_read_running_apps_reads_app_slice_sorted_by_memory(tmp_path):
    base = tmp_path / "user.slice" / "user-1000.slice" / "user@1000.service" / "app.slice"
    small = base / "app-nefes-mousepad-11111111.scope"
    big = base / "app-nefes-firefox-esr-22222222.scope"
    frozen = base / "app-nefes-gimp-33333333.scope"
    for d, mem, ev in (
        (small, 40 * 1024 * 1024, "populated 1\nfrozen 0\n"),
        (big, 350 * 1024 * 1024, "populated 1\nfrozen 0\n"),
        (frozen, 200 * 1024 * 1024, "populated 1\nfrozen 1\n"),
    ):
        d.mkdir(parents=True)
        (d / "memory.current").write_text(f"{mem}\n")
        (d / "cgroup.events").write_text(ev)
    # app.slice dışındaki session-2.scope dahil edilmez
    session = tmp_path / "user.slice" / "user-1000.slice" / "session-2.scope"
    session.mkdir(parents=True)
    (session / "memory.current").write_text("999999999\n")

    apps = read_running_apps(cgroup_root=tmp_path, uid=1000)
    assert [(name, mem, is_frozen) for _path, name, mem, is_frozen in apps] == [
        ("firefox-esr", 350 * 1024 * 1024, False),
        ("gimp", 200 * 1024 * 1024, True),
        ("mousepad", 40 * 1024 * 1024, False),
    ]


def test_read_running_apps_missing_app_slice_returns_empty(tmp_path):
    assert read_running_apps(cgroup_root=tmp_path, uid=1000) == []
