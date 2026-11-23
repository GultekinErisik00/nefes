"""nefes_baslat birim testleri — uygulamaları kendi scope'unda başlatan sarmalayıcı (ADR-0002).

Xfce uygulamaları ayrı cgroup'ta başlatmaz (hepsi session-2.scope'ta); nefesd yalnızca
app.slice altındaki scope'ları dondurabilir. nefes-baslat bu boşluğu kapatır.
"""
import pytest

from nefes_baslat import (
    MARKER,
    install_desktop_files,
    main,
    remove_desktop_files,
    rewrite_desktop,
    systemd_run_argv,
    unit_name,
)

LAUNCHER = "/home/user/nefes/bin/nefes-baslat"


# --- birim adı ------------------------------------------------------------------

@pytest.mark.parametrize(
    "argv, expected",
    [
        (["/usr/lib/firefox-esr/firefox-esr", "%u"], "app-nefes-firefox-esr-1a2b3c4d"),
        (["libreoffice", "--calc"], "app-nefes-libreoffice-1a2b3c4d"),
        (["env", "LANG=tr_TR.UTF-8", "GDK_SCALE=2", "gimp"], "app-nefes-gimp-1a2b3c4d"),
        (["Some App!"], "app-nefes-some-app-1a2b3c4d"),
        (["env", "A=1"], "app-nefes-app-1a2b3c4d"),  # program yok → genel ad
    ],
)
def test_unit_name_uses_the_program_name_and_a_random_suffix(argv, expected):
    assert unit_name(argv, suffix="1a2b3c4d") == expected


def test_systemd_run_argv_starts_the_command_in_its_own_user_scope():
    assert systemd_run_argv(["firefox-esr", "https://pardus.org.tr"], "app-nefes-firefox-esr-1a2b3c4d") == [
        "systemd-run", "--user", "--scope", "--quiet", "--collect",
        "--unit=app-nefes-firefox-esr-1a2b3c4d", "--",
        "firefox-esr", "https://pardus.org.tr",
    ]


# --- .desktop yeniden yazma -------------------------------------------------------

CALC = """[Desktop Entry]
Name=LibreOffice Calc
TryExec=libreoffice
Exec=libreoffice --calc %U
DBusActivatable=true

[Desktop Action NewDocument]
Name=Yeni Çalışma Sayfası
Exec=libreoffice --calc
"""


def test_rewrite_prefixes_every_exec_line_and_marks_the_file():
    out = rewrite_desktop(CALC, LAUNCHER)
    assert f"Exec={LAUNCHER} libreoffice --calc %U\n" in out
    assert f"Exec={LAUNCHER} libreoffice --calc\n" in out
    assert out.count(MARKER) == 1
    assert out.splitlines()[1] == MARKER  # [Desktop Entry] başlığının hemen altında


def test_rewrite_keeps_tryexec_and_disables_dbus_activation():
    out = rewrite_desktop(CALC, LAUNCHER)
    assert "TryExec=libreoffice\n" in out  # program var mı kontrolü değişmez
    assert "DBusActivatable=false\n" in out  # D-Bus etkinleştirmesi Exec'i atlar


def test_rewrite_is_idempotent():
    once = rewrite_desktop(CALC, LAUNCHER)
    assert rewrite_desktop(once, LAUNCHER) == once


def test_rewrite_quotes_a_launcher_path_containing_spaces():
    out = rewrite_desktop("[Desktop Entry]\nExec=gimp %U\n", "/opt/nefes proje/bin/nefes-baslat")
    assert 'Exec="/opt/nefes proje/bin/nefes-baslat" gimp %U\n' in out


def test_rewrite_rejects_text_without_desktop_entry_group():
    with pytest.raises(ValueError):
        rewrite_desktop("Exec=gimp\n", LAUNCHER)


# --- kurma / kaldırma ---------------------------------------------------------------

def make_source(tmp_path):
    src = tmp_path / "share"
    src.mkdir()
    (src / "libreoffice-calc.desktop").write_text(CALC)
    (src / "gimp.desktop").write_text("[Desktop Entry]\nName=GIMP\nExec=gimp-2.10 %U\n")
    return src


def test_install_writes_rewritten_copies_for_found_apps_only(tmp_path):
    src, dst = make_source(tmp_path), tmp_path / "local"
    result = install_desktop_files([src], dst, ["libreoffice-calc", "gimp", "chromium"], LAUNCHER)
    assert result == {"libreoffice-calc": "kuruldu", "gimp": "kuruldu", "chromium": "bulunamadı"}
    assert (dst / "libreoffice-calc.desktop").read_text() == rewrite_desktop(CALC, LAUNCHER)


def test_install_never_overwrites_a_users_own_override(tmp_path):
    src, dst = make_source(tmp_path), tmp_path / "local"
    dst.mkdir()
    (dst / "gimp.desktop").write_text("[Desktop Entry]\nExec=gimp --kendi-ayarim\n")
    result = install_desktop_files([src], dst, ["gimp"], LAUNCHER)
    assert result == {"gimp": "kullanıcının dosyası, dokunulmadı"}
    assert (dst / "gimp.desktop").read_text() == "[Desktop Entry]\nExec=gimp --kendi-ayarim\n"


def test_install_refreshes_its_own_previous_override(tmp_path):
    src, dst = make_source(tmp_path), tmp_path / "local"
    install_desktop_files([src], dst, ["gimp"], "/eski/nefes-baslat")
    install_desktop_files([src], dst, ["gimp"], LAUNCHER)
    assert f"Exec={LAUNCHER} gimp-2.10 %U" in (dst / "gimp.desktop").read_text()


def test_remove_deletes_only_files_written_by_nefes_baslat(tmp_path):
    src, dst = make_source(tmp_path), tmp_path / "local"
    install_desktop_files([src], dst, ["libreoffice-calc"], LAUNCHER)
    (dst / "own.desktop").write_text("[Desktop Entry]\nExec=own\n")
    assert remove_desktop_files(dst) == ["libreoffice-calc.desktop"]
    assert sorted(p.name for p in dst.iterdir()) == ["own.desktop"]


# --- komut satırı: başlatma ------------------------------------------------------------

class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, file, args):
        self.calls.append((file, args))


def test_main_execs_systemd_run_when_available():
    execvp = Recorder()
    main(["firefox-esr", "%u"], execvp=execvp, which=lambda name: f"/usr/bin/{name}",
         user_manager=lambda: True, suffix="1a2b3c4d")
    assert execvp.calls == [("systemd-run", systemd_run_argv(["firefox-esr", "%u"], "app-nefes-firefox-esr-1a2b3c4d"))]


def test_main_runs_the_command_directly_without_systemd_run():
    execvp = Recorder()
    main(["gimp"], execvp=execvp, which=lambda name: None, user_manager=lambda: True, suffix="1a2b3c4d")
    assert execvp.calls == [("gimp", ["gimp"])]


def test_main_runs_the_command_directly_when_the_user_manager_is_down():
    # systemd --user yokken systemd-run başarısız olur ve uygulama HİÇ açılmaz; doğrudan çalıştır.
    execvp = Recorder()
    main(["gimp"], execvp=execvp, which=lambda name: f"/usr/bin/{name}", user_manager=lambda: False)
    assert execvp.calls == [("gimp", ["gimp"])]


def test_main_accepts_a_double_dash_before_the_command():
    execvp = Recorder()
    main(["--", "gimp", "--version"], execvp=execvp, which=lambda name: None, user_manager=lambda: True)
    assert execvp.calls == [("gimp", ["gimp", "--version"])]


def test_main_without_a_command_exits_with_usage_error():
    assert main([], execvp=Recorder(), which=lambda name: None) == 2
