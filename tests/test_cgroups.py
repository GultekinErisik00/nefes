"""cgroups.py birim testleri — sahte cgroup ağacı (tmp_path) üzerinde.

Gerçek /sys/fs/cgroup davranışı (asenkron dondurma, EAGAIN) tests/test_vm.py'de, VM'de sınanır.
"""
import errno
import os

import pytest

from nefesd import cgroups
from nefesd.cgroups import (
    CgroupPathError,
    ScopeGone,
    cgroup_of_pid,
    freeze,
    list_frozen,
    read_apps,
    reclaim,
    thaw,
)
from nefesd.karar import AppCgroup

UID = 1000
APP = "/user.slice/user-1000.slice/user@1000.service/app.slice"
FIREFOX = f"{APP}/app-nefes-firefox-11.scope"
CALC = f"{APP}/app-nefes-libreoffice-12.scope"
NESTED = f"{APP}/app-org.gnome.Terminal.slice/vte-spawn-3.scope"
DCONF = f"{APP}/dconf.service"
SESSION = "/user.slice/user-1000.slice/session-2.scope"


def make_cg(root, path, mem=0, frozen=False):
    d = root / path.lstrip("/")
    d.mkdir(parents=True, exist_ok=True)
    (d / "memory.current").write_text(f"{mem}\n")
    (d / "cgroup.events").write_text(f"populated 1\nfrozen {int(frozen)}\n")
    (d / "cgroup.freeze").write_text("0\n")
    (d / "memory.reclaim").write_text("")
    return d


# --- okuma -------------------------------------------------------------------

def test_read_apps_returns_scopes_under_app_slice_with_memory(tmp_path):
    make_cg(tmp_path, FIREFOX, mem=900)
    make_cg(tmp_path, CALC, mem=300)
    make_cg(tmp_path, NESTED, mem=40)
    make_cg(tmp_path, DCONF, mem=5)
    make_cg(tmp_path, SESSION, mem=5000)

    assert read_apps(tmp_path, UID, {}) == (
        AppCgroup(f"{APP}/app-nefes-firefox-11.scope", 900, None),
        AppCgroup(f"{APP}/app-nefes-libreoffice-12.scope", 300, None),
        AppCgroup(f"{APP}/app-org.gnome.Terminal.slice/vte-spawn-3.scope", 40, None),
    )


def test_read_apps_attaches_known_frozen_since(tmp_path):
    make_cg(tmp_path, FIREFOX, mem=900, frozen=True)
    assert read_apps(tmp_path, UID, {FIREFOX: 123.5}) == (AppCgroup(FIREFOX, 900, 123.5),)


def test_read_apps_skips_scope_that_vanished_mid_scan(tmp_path):
    make_cg(tmp_path, FIREFOX, mem=900)
    gone = make_cg(tmp_path, CALC, mem=300)
    (gone / "memory.current").unlink()  # scope bitti, dosyalar kayboldu
    assert read_apps(tmp_path, UID, {}) == (AppCgroup(FIREFOX, 900, None),)


def test_read_apps_without_app_slice_is_empty(tmp_path):
    make_cg(tmp_path, SESSION, mem=5000)
    assert read_apps(tmp_path, UID, {}) == ()


def test_list_frozen_finds_scopes_marked_frozen_on_disk(tmp_path):
    make_cg(tmp_path, FIREFOX, frozen=True)
    make_cg(tmp_path, CALC, frozen=False)
    assert list_frozen(tmp_path, UID) == (FIREFOX,)


# --- /proc/<pid>/cgroup -------------------------------------------------------

def test_cgroup_of_pid_reads_unified_hierarchy_line(tmp_path):
    (tmp_path / "4321").mkdir()
    (tmp_path / "4321" / "cgroup").write_text(f"1:name=systemd:/legacy\n0::{FIREFOX}\n")
    assert cgroup_of_pid(4321, proc_root=tmp_path) == FIREFOX


def test_cgroup_of_missing_pid_is_none(tmp_path):
    assert cgroup_of_pid(99999, proc_root=tmp_path) is None


# --- yazma: freeze / thaw / reclaim ------------------------------------------

def test_freeze_writes_1_and_thaw_writes_0(tmp_path):
    d = make_cg(tmp_path, FIREFOX)
    freeze(tmp_path, FIREFOX, UID)
    assert (d / "cgroup.freeze").read_text().strip() == "1"
    thaw(tmp_path, FIREFOX, UID)
    assert (d / "cgroup.freeze").read_text().strip() == "0"


@pytest.mark.parametrize("path", [SESSION, DCONF, f"{APP}/../session.slice/x.scope",
                                  "/user.slice/user-0.slice/user@0.service/app.slice/x.scope"])
def test_freeze_refuses_paths_that_are_not_this_users_app_scopes(tmp_path, path):
    d = make_cg(tmp_path, path)  # hedef gerçekten var: yalnızca doğrulama durdurabilir
    with pytest.raises(CgroupPathError):
        freeze(tmp_path, path, UID)
    assert (d / "cgroup.freeze").read_text().strip() == "0"


def test_freeze_refuses_symlinked_intermediate_slice(tmp_path):
    outside = make_cg(tmp_path, "/elsewhere.slice/inner.scope")
    (tmp_path / APP.lstrip("/")).mkdir(parents=True)
    (tmp_path / APP.lstrip("/") / "evil.slice").symlink_to(tmp_path / "elsewhere.slice")
    with pytest.raises(CgroupPathError):
        freeze(tmp_path, f"{APP}/evil.slice/inner.scope", UID)
    assert (outside / "cgroup.freeze").read_text().strip() == "0"


def test_read_apps_does_not_follow_symlinked_scopes_or_slices(tmp_path):
    make_cg(tmp_path, FIREFOX, mem=900)
    make_cg(tmp_path, "/elsewhere.slice/inner.scope", mem=5000)
    app_dir = tmp_path / APP.lstrip("/")
    (app_dir / "evil.slice").symlink_to(tmp_path / "elsewhere.slice")
    (app_dir / "evil.scope").symlink_to(tmp_path / "elsewhere.slice" / "inner.scope")
    assert read_apps(tmp_path, UID, {}) == (AppCgroup(FIREFOX, 900, None),)


def test_freeze_on_vanished_scope_raises_scope_gone(tmp_path):
    with pytest.raises(ScopeGone):
        freeze(tmp_path, FIREFOX, UID)


def test_freeze_does_not_create_missing_interface_file(tmp_path):
    d = make_cg(tmp_path, FIREFOX)
    (d / "cgroup.freeze").unlink()
    with pytest.raises(ScopeGone):
        freeze(tmp_path, FIREFOX, UID)
    assert not (d / "cgroup.freeze").exists()


def test_freeze_refuses_symlink_that_escapes_the_app_scope(tmp_path):
    target = make_cg(tmp_path, SESSION)
    link = tmp_path / FIREFOX.lstrip("/")
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(CgroupPathError):
        freeze(tmp_path, FIREFOX, UID)
    assert (target / "cgroup.freeze").read_text().strip() == "0"


def test_reclaim_writes_requested_bytes_and_reports_freed_amount(tmp_path):
    d = make_cg(tmp_path, FIREFOX, mem=1000)
    result = reclaim(tmp_path, FIREFOX, UID, 600)
    assert (d / "memory.reclaim").read_text().strip() == "600"
    assert result.requested == 600
    assert result.before == 1000
    assert result.after == 1000  # sahte dosya değişmez; gerçek düşüş VM testinde
    assert result.complete is True


def test_reclaim_eagain_is_reported_as_partial_not_raised(tmp_path, monkeypatch):
    make_cg(tmp_path, FIREFOX, mem=1000)
    real_write = os.write

    def write_eagain_for_reclaim(fd, data):
        if data == b"5000":
            raise OSError(errno.EAGAIN, "Resource temporarily unavailable")
        return real_write(fd, data)

    monkeypatch.setattr(cgroups.os, "write", write_eagain_for_reclaim)
    assert reclaim(tmp_path, FIREFOX, UID, 5000).complete is False


def test_reclaim_other_write_errors_propagate(tmp_path, monkeypatch):
    make_cg(tmp_path, FIREFOX, mem=1000)

    def write_einval(fd, data):
        raise OSError(errno.EINVAL, "Invalid argument")

    monkeypatch.setattr(cgroups.os, "write", write_einval)
    with pytest.raises(OSError) as info:
        reclaim(tmp_path, FIREFOX, UID, 600)
    assert info.value.errno == errno.EINVAL


def test_reclaim_on_vanished_scope_raises_scope_gone(tmp_path):
    with pytest.raises(ScopeGone):
        reclaim(tmp_path, FIREFOX, UID, 600)


def test_reclaim_refuses_non_positive_amount(tmp_path):
    make_cg(tmp_path, FIREFOX, mem=1000)
    with pytest.raises(ValueError):
        reclaim(tmp_path, FIREFOX, UID, 0)
