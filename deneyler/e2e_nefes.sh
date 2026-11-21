#!/usr/bin/env bash
# Nefes uçtan uca deney: gerçek bellek baskısı altında nefesd bir arka plan uygulamasını dondurur mu?
# Pardus VM'de, masaüstü kullanıcısı olarak (root gerekmez):  bash deneyler/e2e_nefes.sh
#  1) nefesd'yi başlatır (X11 odak için DISPLAY=:0)
#  2) "arka plan uygulaması": kendi scope'unda 500 MB tutan, her saniye sayfalarına dokunan süreç
#  3) "ön plandaki iş": stress-ng 1100 MB (ssh oturum scope'unda → aday değil)
#  4) baskı biterken ve nefesd SIGTERM ile dururken uygulamanın çözüldüğünü doğrular
set -uo pipefail
cd "$(dirname "$0")/.."
NEFES_LOG=$(mktemp /tmp/nefesd-e2e.XXXX)
HOG_LOG=$(mktemp /tmp/nefes-hog.XXXX)
UNIT="app-nefes-e2e-hog-$$"
APP_SLICE="/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/app.slice"
HOG_MB=${HOG_MB:-500}
STRESS_MB=${STRESS_MB:-1100}

cleanup() {
  [ -n "${NEFES_PID:-}" ] && kill "$NEFES_PID" 2>/dev/null
  [ -d "$APP_SLICE/$UNIT.scope" ] && echo 0 > "$APP_SLICE/$UNIT.scope/cgroup.freeze" 2>/dev/null
  systemctl --user stop "$UNIT.scope" 2>/dev/null || true
}
trap cleanup EXIT

frozen() { awk '/^frozen/{print $2}' "$APP_SLICE/$UNIT.scope/cgroup.events" 2>/dev/null || echo "-"; }
mem_mb() { echo $(( $(cat "$APP_SLICE/$UNIT.scope/memory.current" 2>/dev/null || echo 0) / 1048576 )); }

# Önce uygulama belleğini doldursun; nefesd ondan sonra başlasın (yoksa uygulamanın kendi
# 500 MB'lık ayırması baskı yaratır ve stress-ng başlamadan dondurulur — 2026-11-21 1. çalıştırma).
systemd-run --user --scope --quiet --unit="$UNIT" python3 -c '
import mmap, os, sys, time
n = int(sys.argv[1]) * 1024 * 1024
buf = mmap.mmap(-1, n, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)
pages = [os.urandom(1024) + bytes(3072) for _ in range(64)]
for k, i in enumerate(range(0, n, 4096)): buf[i:i + 4096] = pages[k % 64]
log = open(sys.argv[2], "a", buffering=1)
while True:
    t0 = time.monotonic()
    for i in range(0, n, 4096): buf[i] = (buf[i] + 1) & 0xFF
    log.write(f"{time.time():.1f} touch {(time.monotonic() - t0) * 1000:.0f}ms\n")
    time.sleep(1)
' "$HOG_MB" "$HOG_LOG" &
for _ in $(seq 60); do grep -q touch "$HOG_LOG" 2>/dev/null && break; sleep 0.5; done
sleep 5  # ayırmanın yarattığı PSI dalgası sönsün

DISPLAY=:0 python3 -m nefesd --log-level DEBUG >"$NEFES_LOG" 2>&1 &
NEFES_PID=$!
sleep 2
echo "[0] başlangıç: uygulama ${HOG_MB} MB, scope bellek $(mem_mb) MB, frozen=$(frozen)"

echo "[1] stress-ng ${STRESS_MB} MB, 25 s (ön plandaki iş)"
stress-ng --vm 1 --vm-bytes "${STRESS_MB}M" --vm-keep --timeout 25s --quiet &
STRESS_PID=$!
for t in 3 6 9 12 15 18 21 24; do
  sleep 3
  echo "    t=${t}s  frozen=$(frozen)  scope bellek=$(mem_mb) MB  psi: $(head -1 /proc/pressure/memory | cut -d' ' -f2)"
done
wait "$STRESS_PID"; echo "    stress-ng bitti (çıkış $?)"

echo "[2] baskı bitti, güvenli seviyede çözülmesi bekleniyor (en çok 30 s)"
for _ in $(seq 30); do [ "$(frozen)" = 0 ] && break; sleep 1; done
echo "    frozen=$(frozen)  scope bellek=$(mem_mb) MB"

echo "[3] nefesd SIGTERM"
kill -TERM "$NEFES_PID"; wait "$NEFES_PID"; NEFES_PID=""
echo "    frozen=$(frozen) (0 olmalı)"

echo; echo "== nefesd günlüğü =="; grep -vE "baskı: tetik=False" "$NEFES_LOG" | tail -30
echo; echo "== uygulamanın en uzun dokunma süreleri (donukken dokunamaz) =="
sed 's/ms$//' "$HOG_LOG" | sort -k3 -n -r | head -3
