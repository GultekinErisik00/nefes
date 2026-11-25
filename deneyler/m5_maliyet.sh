#!/usr/bin/env bash
# M5 — nefesd servis maliyeti: CPU (%) ve RSS (MB), boşta ve baskı altında (hedef: CPU < %1, RSS < 30 MB).
# Pardus'ta, nefesd kullanıcı servisi çalışırken (root gerekmez):  bash deneyler/m5_maliyet.sh [SÜRE=60]
# CPU: /proc/<pid>/stat utime+stime farkı / geçen süre; RSS: /proc/<pid>/status VmRSS (her saniye, tepe).
set -uo pipefail
cd "$(dirname "$0")/.."
SURE=${1:-60}
PID=$(systemctl --user show nefesd.service -p MainPID --value)
[ "${PID:-0}" -gt 0 ] || { echo "nefesd çalışmıyor (systemctl --user start nefesd)"; exit 1; }
HZ=$(getconf CLK_TCK)

olc() {  # $1 = etiket
  local t0 c0 c1 rss max=0
  c0=$(awk '{print $14 + $15}' /proc/$PID/stat); t0=$(date +%s.%N)
  for _ in $(seq "$SURE"); do
    rss=$(awk '/^VmRSS/{print $2}' /proc/$PID/status); [ "$rss" -gt "$max" ] && max=$rss
    sleep 1
  done
  c1=$(awk '{print $14 + $15}' /proc/$PID/stat)
  python3 -c "import sys; c0,c1,t0,hz,mx=map(float,sys.argv[1:6]); import time; el=time.time()-t0
print(f'$1: CPU %{(c1-c0)/hz/el*100:.2f}  RSS tepe {mx/1024:.1f} MB  ({el:.0f} s)')" "$c0" "$c1" "$t0" "$HZ" "$max"
}

echo "nefesd PID $PID"
olc "boşta  "
BASLAT=$(command -v nefes-baslat || echo bin/nefes-baslat)
"$BASLAT" python3 -c '
import mmap, os, time
n = 400 * 1024 * 1024
buf = mmap.mmap(-1, n, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)
page = os.urandom(1024) + bytes(3072)
for i in range(0, n, 4096): buf[i:i + 4096] = page
while True:
    for i in range(0, n, 4096): buf[i] = (buf[i] + 1) & 0xFF
    time.sleep(2)
' >/dev/null 2>&1 & HOG=$!
sleep 8
stress-ng --vm 1 --vm-bytes 1500M --vm-keep --timeout "$((SURE + 5))s" --quiet >/dev/null 2>&1 & ST=$!
olc "baskıda"
wait "$ST" 2>/dev/null
APP_SLICE="/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/app.slice"
for s in "$APP_SLICE"/app-nefes-python3-*.scope; do [ -d "$s" ] && echo 0 > "$s/cgroup.freeze"; done 2>/dev/null
kill "$HOG" 2>/dev/null; wait 2>/dev/null
journalctl --user -u nefesd --since "-$((2 * SURE + 20))s" --no-pager -o cat | grep -cE "DONDURULDU" | xargs -I{} echo "baskı sırasında dondurma: {}"
