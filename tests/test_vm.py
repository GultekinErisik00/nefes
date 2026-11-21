"""Gerçek cgroup v2 / PSI ile entegrasyon testleri — yalnızca Pardus VM'de.

Çalıştırma (VM'de, root gerekmez):  NEFES_VM=1 python3 -m pytest -q tests/test_vm.py
Her test kendi `app-nefes-test-*` scope'unu açar ve kapatır; başka hiçbir cgroup'a yazmaz.
"""
import os
import select
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from nefesd.cgroups import cgroup_of_pid, freeze, list_frozen, read_apps, reclaim, thaw
from nefesd.karar import app_scope_parts
from nefesd.psi import parse_pressure, trigger_line

pytestmark = pytest.mark.skipif(
    os.environ.get("NEFES_VM") != "1" or not sys.platform.startswith("linux"),
    reason="yalnızca Pardus VM'de, NEFES_VM=1 ile",
)

ROOT = Path("/sys/fs/cgroup")
UID = os.getuid()
MB = 1024 * 1024
WORKER = (
    "import mmap, os, sys, time\n"
    "n = int(sys.argv[1]) * 1024 * 1024\n"
    "buf = mmap.mmap(-1, n, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)\n"
    "page = os.urandom(1024) + bytes(3072)\n"
    "for i in range(0, n, 4096): buf[i:i + 4096] = page\n"
    "print('READY', flush=True)\n"
    "time.sleep(120)\n"
)


@pytest.fixture
def app_scope():
    unit = f"app-nefes-test-{uuid.uuid4().hex[:8]}"
    proc = subprocess.Popen(
        ["systemd-run", "--user", "--scope", "--quiet", f"--unit={unit}",
         sys.executable, "-c", WORKER, "64"],
        stdout=subprocess.PIPE, text=True,
    )
    try:
        assert proc.stdout.readline().strip() == "READY"
        path = cgroup_of_pid(proc.pid)
        yield path
    finally:
        if path := cgroup_of_pid(proc.pid):
            thaw(ROOT, path, UID)  # donuk süreç SIGTERM'i işleyemez
        proc.terminate()
        proc.wait(timeout=10)
        subprocess.run(["systemctl", "--user", "stop", f"{unit}.scope"], check=False)


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_systemd_run_scope_is_a_valid_app_scope(app_scope):
    assert app_scope_parts(app_scope, UID) is not None


def test_read_apps_sees_the_scope_and_its_memory(app_scope):
    apps = {a.path: a for a in read_apps(ROOT, UID, {})}
    assert app_scope in apps
    assert apps[app_scope].memory_current >= 60 * MB


def test_freeze_and_thaw_change_kernel_frozen_state(app_scope):
    freeze(ROOT, app_scope, UID)
    assert wait_until(lambda: app_scope in list_frozen(ROOT, UID))
    thaw(ROOT, app_scope, UID)
    assert wait_until(lambda: app_scope not in list_frozen(ROOT, UID))


def test_reclaim_more_than_usage_is_partial_but_frees_memory(app_scope):
    freeze(ROOT, app_scope, UID)
    result = reclaim(ROOT, app_scope, UID, 512 * MB)
    assert result.complete is False  # çekirdek EAGAIN döndü: 512 MB yoktu
    assert result.after < result.before - 32 * MB


def test_kernel_accepts_unprivileged_psi_trigger_line():
    fd = os.open("/proc/pressure/memory", os.O_RDWR | os.O_NONBLOCK)
    try:
        os.write(fd, trigger_line("some", 500_000, 2_000_000))
        poller = select.poll()
        poller.register(fd, select.POLLPRI)
        events = poller.poll(100)
        assert all(ev & select.POLLERR == 0 for _, ev in events)
    finally:
        os.close(fd)


def test_parse_pressure_reads_the_real_proc_file():
    stats = parse_pressure(Path("/proc/pressure/memory").read_text())
    assert stats.some_total >= 0 and stats.some_avg10 >= 0.0
