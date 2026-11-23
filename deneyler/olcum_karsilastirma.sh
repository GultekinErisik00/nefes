#!/usr/bin/env bash
# Ölçüm turu önizlemesi: aynı yük senaryosu Nefes KAPALI ve AÇIK, M1/M2 karşılaştırması.
# Pardus'ta, masaüstü kullanıcısı olarak:  bash deneyler/olcum_karsilastirma.sh [TEKRAR]
# Senaryo: 500 MB'lık arka plan uygulaması (nefes-baslat ile, her saniye sayfalarına dokunur)
#          + 5. saniyede stress-ng 1500 MB, 30 s ("ön plandaki iş"); prob 45 s kayıt yapar.
# Çıktı: olcumler/<tarih>/{kapali,acik}-N/{prob,psi}.csv ve özet tablo.
set -uo pipefail
cd "$(dirname "$0")/.."
export DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"
TEKRAR=${1:-1}
OUT="olcumler/$(date +%Y%m%d-%H%M)"
APP_SLICE="/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/app.slice"
mkdir -p "$OUT"

cleanup() {
  kill ${NEFES_PID:-} ${HOG_PID:-} 2>/dev/null
  for s in "$APP_SLICE"/app-nefes-python3-*.scope; do [ -d "$s" ] && echo 0 > "$s/cgroup.freeze"; done 2>/dev/null
  wait 2>/dev/null
}
trap cleanup EXIT

run() {  # $1 = kapali | acik, $2 = tekrar no
  bin/nefes-baslat python3 -c '
import mmap, os, time
n = 500 * 1024 * 1024
buf = mmap.mmap(-1, n, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)
page = os.urandom(1024) + bytes(3072)
for i in range(0, n, 4096): buf[i:i + 4096] = page
while True:
    for i in range(0, n, 4096): buf[i] = (buf[i] + 1) & 0xFF
    time.sleep(1)
' & HOG_PID=$!
  sleep 8
  if [ "$1" = acik ]; then python3 -m nefesd --no-dbus >"$OUT/$1-$2.nefesd.log" 2>&1 & NEFES_PID=$!; sleep 1; fi
  python3 -m nefes_olcum kaydet --cikti "$OUT/$1-$2" --sure 45 &
  PROBE=$!
  sleep 5
  stress-ng --vm 1 --vm-bytes 1500M --vm-keep --timeout 30s --quiet
  wait "$PROBE"
  [ -n "${NEFES_PID:-}" ] && { kill "$NEFES_PID"; wait "$NEFES_PID" 2>/dev/null; NEFES_PID=""; }
  kill "$HOG_PID" 2>/dev/null; wait "$HOG_PID" 2>/dev/null; HOG_PID=""
  sleep 10  # sistem toparlansın (zram boşalsın)
}

for n in $(seq "$TEKRAR"); do
  echo "== tekrar $n: Nefes kapalı"; run kapali "$n"
  echo "== tekrar $n: Nefes açık";   run acik "$n"
done
echo; python3 -m nefes_olcum ozet "$OUT"/kapali-[0-9]*/ "$OUT"/acik-[0-9]*/  # yalnızca klasörler (.log değil)
echo; echo "Ham veri: $OUT"; grep -h "DONDURULDU\|DEVAM" "$OUT"/*.nefesd.log 2>/dev/null
