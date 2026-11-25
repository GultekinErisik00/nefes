"""nefes_agent.sistem — /proc/meminfo ve zram mm_stat ayrıştırma (root gerekmez)."""
from nefes_agent.sistem import parse_meminfo, parse_mm_stat, read_memory

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
