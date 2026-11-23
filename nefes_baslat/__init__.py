"""nefes-baslat — uygulamaları kendi systemd scope'unda başlatır (ADR-0002).

Xfce uygulamaları ayrı cgroup'ta başlatmaz: hepsi pencere yöneticisiyle aynı session-2.scope'ta
kalır ve nefesd onları dondurmaz (dondurmamalı). nefes-baslat bir uygulamayı
`systemd-run --user --scope --unit=app-nefes-<ad>-<rastgele>` ile başlatır; uygulama
user@UID.service/app.slice altında kendi scope'una girer ve aday olabilir.

  nefes-baslat firefox-esr %u            # tek uygulama
  nefes-baslat --desktop-install [ad…]   # menü/panel başlatıcılarını sarmala (~/.local/share/applications)
  nefes-baslat --desktop-remove          # yalnızca nefes-baslat'ın yazdığı kopyaları sil

Güvenlik: systemd-run ya da kullanıcı yöneticisi yoksa komut doğrudan çalıştırılır — uygulama
her durumda açılır, yalnızca aday olmaz. Kullanıcının kendi .desktop kopyalarına dokunulmaz.
"""
from __future__ import annotations

import os
import re
import secrets
import shutil
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

MARKER = "X-Nefes-Baslat=true"
DEFAULT_APPS = (
    "firefox-esr", "firefox", "chromium", "thunderbird", "gimp",
    "libreoffice-startcenter", "libreoffice-writer", "libreoffice-calc",
    "libreoffice-impress", "libreoffice-draw",
)
SOURCE_DIRS = (Path("/usr/share/applications"), Path("/usr/local/share/applications"))


def unit_name(argv: list[str], suffix: str) -> str:
    """app-nefes-<program>-<son ek>; program adı `env VAR=… prog` biçiminden de çıkarılır."""
    program = _program(argv)
    base = re.sub(r"[^a-z0-9]+", "-", Path(program).name.lower()).strip("-") if program else ""
    return f"app-nefes-{base or 'app'}-{suffix}"


def systemd_run_argv(argv: list[str], unit: str) -> list[str]:
    return ["systemd-run", "--user", "--scope", "--quiet", "--collect", f"--unit={unit}", "--", *argv]


def rewrite_desktop(text: str, launcher: str) -> str:
    """Her Exec= satırının başına sarmalayıcıyı ekler, D-Bus etkinleştirmesini kapatır, işaret koyar."""
    lines = text.splitlines()
    if "[Desktop Entry]" not in (line.strip() for line in lines):
        raise ValueError(".desktop dosyasında [Desktop Entry] grubu yok")
    prefix = f'"{launcher}"' if " " in launcher else launcher
    has_marker = MARKER in lines
    out = []
    for line in lines:
        if line.startswith("Exec=") and not line[5:].startswith(prefix + " ") and line[5:] != prefix:
            line = f"Exec={prefix} {line[5:]}"
        elif line.strip() == "DBusActivatable=true":
            line = "DBusActivatable=false"  # D-Bus ile etkinleştirme Exec'i atlar → sarmalayıcı devre dışı kalırdı
        out.append(line)
        if line.strip() == "[Desktop Entry]" and not has_marker:
            out.append(MARKER)
            has_marker = True
    return "\n".join(out) + "\n"


def install_desktop_files(source_dirs: Iterable[Path], target_dir: Path,
                          names: Iterable[str], launcher: str) -> dict[str, str]:
    """Bulunan uygulamaların sarmalanmış kopyalarını yazar; kullanıcının kendi kopyasını ezmez."""
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    for name in names:
        source = next((Path(d) / f"{name}.desktop" for d in source_dirs
                       if (Path(d) / f"{name}.desktop").is_file()), None)
        target = target_dir / f"{name}.desktop"
        if source is None:
            result[name] = "bulunamadı"
        elif target.exists() and not _is_ours(target):
            result[name] = "kullanıcının dosyası, dokunulmadı"
        else:
            target.write_text(rewrite_desktop(source.read_text(encoding="utf-8"), launcher), encoding="utf-8")
            result[name] = "kuruldu"
    return result


def remove_desktop_files(target_dir: Path) -> list[str]:
    """Yalnızca nefes-baslat'ın yazdığı (işaretli) kopyaları siler."""
    target_dir = Path(target_dir)
    if not target_dir.is_dir():
        return []
    removed = []
    for path in sorted(target_dir.glob("*.desktop")):
        if _is_ours(path):
            path.unlink()
            removed.append(path.name)
    return removed


def main(argv: list[str] | None = None,
         execvp: Callable[[str, list[str]], None] = os.execvp,
         which: Callable[[str], str | None] = shutil.which,
         user_manager: Callable[[], bool] | None = None,
         suffix: str | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["--desktop-install"]:
        return _cli_install(args[1:], which)
    if args[:1] == ["--desktop-remove"]:
        for name in remove_desktop_files(_target_dir()):
            print(f"kaldırıldı: {name}")
        return 0
    if args[:1] == ["--"]:
        args = args[1:]
    if not args:
        print("kullanım: nefes-baslat <komut> [argümanlar…] | --desktop-install [ad…] | --desktop-remove",
              file=sys.stderr)
        return 2
    manager_up = user_manager or _user_manager_up
    if which("systemd-run") and manager_up():
        execvp("systemd-run", systemd_run_argv(args, unit_name(args, suffix or secrets.token_hex(4))))
    else:
        execvp(args[0], args)
    return 0  # yalnızca testlerde (gerçek execvp geri dönmez)


def _program(argv: list[str]) -> str | None:
    rest = list(argv)
    if rest and Path(rest[0]).name == "env":
        rest = rest[1:]
        while rest and ("=" in rest[0] or rest[0].startswith("-")):
            rest = rest[1:]
    return rest[0] if rest else None


def _is_ours(path: Path) -> bool:
    try:
        return MARKER in path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return False


def _user_manager_up() -> bool:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return Path(runtime, "systemd", "private").exists()


def _target_dir() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data_home) / "applications"


def _default_launcher(which: Callable[[str], str | None]) -> str:
    return which("nefes-baslat") or str(Path(__file__).resolve().parent.parent / "bin" / "nefes-baslat")


def _cli_install(names: list[str], which: Callable[[str], str | None]) -> int:
    launcher = _default_launcher(which)
    result = install_desktop_files(SOURCE_DIRS, _target_dir(), names or DEFAULT_APPS, launcher)
    for name, status in result.items():
        print(f"{name}: {status}")
    print(f"başlatıcı: {launcher}")
    return 0
