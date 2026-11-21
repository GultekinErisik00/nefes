#!/usr/bin/env bash
# Nefes Deney 02: freeze_spike under disk swap vs zram (lz4, zstd).
# Run as root ONCE (one sudo prompt):  sudo bash ~/nefes-deney/zram_deney.sh
# - installs test tools (git, pytest, stress-ng)
# - for each algorithm: builds a temporary zram swap (prio 100, above disk swap), runs the
#   unprivileged spike as the desktop user, then tears zram down
# - leaves the machine as it was (disk swap only); output -> /tmp/nefes-zram-deney.log
set -uo pipefail
USER_NAME=${SUDO_USER:-user}
USER_ID=$(id -u "$USER_NAME")
DIR=$(cd "$(dirname "$0")" && pwd)
OUT=/tmp/nefes-zram-deney.log
MB=${MB:-400}
ZRAM_SIZE=${ZRAM_SIZE:-1G}

[ "$(id -u)" -eq 0 ] || { echo "root olarak çalıştırın: sudo bash $0"; exit 1; }
exec > >(tee "$OUT") 2>&1
chmod 644 "$OUT"

echo "== araçlar =="
dpkg -s git python3-pytest stress-ng >/dev/null 2>&1 || apt-get install -y -q git python3-pytest stress-ng >/dev/null
dpkg -s git python3-pytest stress-ng >/dev/null 2>&1 && echo "git, pytest, stress-ng kurulu"

ZDEV=""
# zramctl --reset also hot-removes the device on this util-linux, so each run creates a
# fresh one with --find and tears down only the device it created.
zram_down() {
  if [ -n "$ZDEV" ] && [ -e "$ZDEV" ]; then swapoff "$ZDEV" 2>/dev/null; zramctl --reset "$ZDEV" 2>/dev/null; fi
  ZDEV=""
}
run_spike() {
  sudo -u "$USER_NAME" XDG_RUNTIME_DIR=/run/user/$USER_ID \
       DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$USER_ID/bus \
       bash "$DIR/freeze_spike.sh" "$MB"
}
trap zram_down EXIT

modprobe zram
echo "vm.swappiness=$(cat /proc/sys/vm/swappiness)"

if [ "${SKIP_DISK:-0}" != 1 ]; then
  echo; echo "===== A) disk swap (zram yok) ====="
  swapon --show
  run_spike
fi

for ALG in lz4 zstd; do
  echo; echo "===== B) zram $ALG ($ZRAM_SIZE, prio 100) ====="
  zram_down
  if ! ZDEV=$(zramctl --find --algorithm "$ALG" --size "$ZRAM_SIZE"); then echo "zram $ALG oluşturulamadı, atlandı"; ZDEV=""; continue; fi
  mkswap -q "$ZDEV" && swapon -p 100 "$ZDEV"
  swapon --show
  run_spike
  echo "zram istatistik: $(zramctl --output NAME,ALGORITHM,DATA,COMPR,TOTAL --noheadings "$ZDEV")"
done

zram_down
echo; echo "== bitti; zram kaldırıldı, sistem eski hâlinde =="; swapon --show
