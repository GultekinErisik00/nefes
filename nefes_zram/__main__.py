"""python3 -m nefes_zram — RAM'e göre /etc/systemd/zram-generator.conf yazar.

  python3 -m nefes_zram --print        # yalnızca göster (root gerekmez)
  sudo python3 -m nefes_zram           # yaz; sonra: systemctl daemon-reload &&
                                       #             systemctl restart systemd-zram-setup@zram0
Gerekli paket: systemd-zram-generator.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nefes_zram import ForeignConfigError, parse_meminfo, render_config, write_config

DEFAULT_OUTPUT = Path("/etc/systemd/zram-generator.conf")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="nefes-zram", description="RAM'e göre zram yapılandırması")
    p.add_argument("--print", action="store_true", help="yazmadan yapılandırmayı göster")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--meminfo", type=Path, default=Path("/proc/meminfo"))
    p.add_argument("--force", action="store_true", help="nefes-zram'a ait olmayan dosyanın üzerine yaz")
    args = p.parse_args(sys.argv[1:] if argv is None else argv)

    try:
        content = render_config(parse_meminfo(args.meminfo.read_text()))
    except (OSError, ValueError) as exc:
        print(f"nefes-zram: RAM okunamadı: {exc}", file=sys.stderr)
        return 1
    if args.print:
        print(content, end="")
        return 0
    try:
        write_config(args.output, content, force=args.force)
    except ForeignConfigError as exc:
        print(f"nefes-zram: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"nefes-zram: yazılamadı ({exc}); root olarak çalıştırın", file=sys.stderr)
        return 1
    print(f"Yazıldı: {args.output}\nEtkinleştirmek için: "
          "systemctl daemon-reload && systemctl restart systemd-zram-setup@zram0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
