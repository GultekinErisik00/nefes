#!/usr/bin/env bash
# Nefes D-Bus uçtan uca: gerçek oturum veriyolunda sözleşme (ADR-0003) çalışıyor mu?
# Pardus'ta, masaüstü kullanıcısı olarak:  bash deneyler/dbus_e2e.sh
#  - nefesd'yi başlatır, arayüzü gdbus ile inceler, sinyalleri izler
#  - baskı altında uygulama donunca ListFrozen ve Resume'u D-Bus üzerinden çağırır
# nefes-agent'ı yazan taraf için de örnek: hangi çağrı/sinyal nasıl görünür.
set -uo pipefail
cd "$(dirname "$0")/.."
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"
BUS=tr.edu.bil461.Nefes1
OBJ=/tr/edu/bil461/Nefes1
IFACE=tr.edu.bil461.Nefes1.Manager
NEFES_LOG=$(mktemp /tmp/nefes-dbus-nefesd.XXXX)
MON_LOG=$(mktemp /tmp/nefes-dbus-monitor.XXXX)
UNIT="app-nefes-dbus-hog-$$"
APP_SLICE="/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/app.slice"
SCOPE_PATH="/user.slice/user-$(id -u).slice/user@$(id -u).service/app.slice/$UNIT.scope"

cleanup() {
  [ -n "${MON_PID:-}" ] && kill "$MON_PID" 2>/dev/null
  [ -n "${NEFES_PID:-}" ] && kill "$NEFES_PID" 2>/dev/null && wait "$NEFES_PID" 2>/dev/null
  [ -d "$APP_SLICE/$UNIT.scope" ] && echo 0 > "$APP_SLICE/$UNIT.scope/cgroup.freeze" 2>/dev/null
  systemctl --user stop "$UNIT.scope" 2>/dev/null || true
}
trap cleanup EXIT
frozen() { awk '/^frozen/{print $2}' "$APP_SLICE/$UNIT.scope/cgroup.events" 2>/dev/null || echo "-"; }

systemd-run --user --scope --quiet --unit="$UNIT" python3 -c '
import mmap, os, time
n = 400 * 1024 * 1024
buf = mmap.mmap(-1, n, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)
page = os.urandom(1024) + bytes(3072)
for i in range(0, n, 4096): buf[i:i + 4096] = page
while True: time.sleep(1)
' &
sleep 6

DISPLAY=:0 python3 -m nefesd --log-level INFO >"$NEFES_LOG" 2>&1 &
NEFES_PID=$!
for _ in $(seq 20); do gdbus introspect --session --dest "$BUS" --object-path "$OBJ" >/dev/null 2>&1 && break; sleep 0.5; done

echo "== [1] arayüz (gdbus introspect)"
gdbus introspect --session --dest "$BUS" --object-path "$OBJ" | sed -n "/interface $IFACE/,/^    };/p"

gdbus monitor --session --dest "$BUS" >"$MON_LOG" 2>&1 &
MON_PID=$!
sleep 1

echo "== [2] baskı: stress-ng 1100 MB (uygulama donmalı)"
stress-ng --vm 1 --vm-bytes 1100M --vm-keep --timeout 15s --quiet &
STRESS=$!
for _ in $(seq 30); do [ "$(frozen)" = 1 ] && break; sleep 0.5; done
echo "    frozen=$(frozen)"

echo "== [3] ListFrozen (D-Bus)"
gdbus call --session --dest "$BUS" --object-path "$OBJ" --method "$IFACE.ListFrozen"

echo "== [4] Resume('$UNIT.scope') (D-Bus) — 'Devam ettir' düğmesinin yapacağı çağrı"
gdbus call --session --dest "$BUS" --object-path "$OBJ" --method "$IFACE.Resume" "$SCOPE_PATH"
sleep 0.5
echo "    frozen=$(frozen) (0 olmalı)"
echo "== [5] tanımadığı yol için Resume → false olmalı"
gdbus call --session --dest "$BUS" --object-path "$OBJ" --method "$IFACE.Resume" "/user.slice/yok.scope"

wait "$STRESS" 2>/dev/null
sleep 1
kill "$MON_PID" 2>/dev/null; MON_PID=""
echo; echo "== [6] izlenen sinyaller (gdbus monitor)"
grep -E "AppFrozen|AppResumed" "$MON_LOG" || echo "    (sinyal görülmedi!)"
echo; echo "== nefesd günlüğü"; grep -E "D-Bus|DONDURULDU|DEVAM|ERROR" "$NEFES_LOG"
