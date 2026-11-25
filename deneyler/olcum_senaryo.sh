#!/usr/bin/env bash
# Ölçüm turunun TEK çalıştırması (masaüstü kullanıcısı olarak; olcum_turu.sh çağırır).
#   bash deneyler/olcum_senaryo.sh <çıktı-klasörü>
# Yük: 3 arka plan "uygulaması" (300+300+200 MB, nefes-baslat ile kendi scope'unda, 2 s'de bir
# sayfalarına dokunur — sekme/uygulama benzeri) + 5. saniyede ön plan işi stress-ng 1500 MB, 40 s
# (1300 MB varsayılan Pardus'u yeterince zorlamadı: M2 ort. 0,3 s, earlyoom hiç tetiklenmedi — Deney 05/1)
# (kullanıcının üzerinde çalıştığı Calc yerine). Prob 60 s kayıt.
# M3 (olen_uygulama.txt) = ölen arka plan uygulaması + öldürülen ön plan işi (0/1).
set -uo pipefail
OUT=$1
cd "$(dirname "$0")/.."
mkdir -p "$OUT"
BASLAT=$(command -v nefes-baslat || echo bin/nefes-baslat)
APP_SLICE="/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/app.slice"
PIDS=()
for mb in 300 300 200; do
  "$BASLAT" python3 -c '
import mmap, os, sys, time
n = int(sys.argv[1]) * 1024 * 1024
buf = mmap.mmap(-1, n, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)
page = os.urandom(1024) + bytes(3072)
for i in range(0, n, 4096): buf[i:i + 4096] = page
while True:
    for i in range(0, n, 4096): buf[i] = (buf[i] + 1) & 0xFF
    time.sleep(2)
' "$mb" >/dev/null 2>&1 &
  PIDS+=($!)
done
sleep 10

nefes-olcum kaydet --cikti "$OUT" --sure 60 >/dev/null &
PROBE=$!
sleep 5
stress-ng --vm 1 --vm-bytes 1500M --vm-keep --timeout 40s --quiet >/dev/null 2>&1
STRESS_RC=$?
wait "$PROBE"

dead=0
for p in "${PIDS[@]}"; do kill -0 "$p" 2>/dev/null || dead=$((dead + 1)); done
[ "$STRESS_RC" -ne 0 ] && dead=$((dead + 1))
echo "$dead" > "$OUT/olen_uygulama.txt"
echo "arka plan ölen: $((dead - (STRESS_RC != 0))), ön plan işi kodu: $STRESS_RC" > "$OUT/notlar.txt"

# temizlik: donuk kalan varsa çöz, sonra sonlandır
for s in "$APP_SLICE"/app-nefes-python3-*.scope; do [ -d "$s" ] && echo 0 > "$s/cgroup.freeze"; done 2>/dev/null
kill "${PIDS[@]}" 2>/dev/null
wait 2>/dev/null
exit 0
