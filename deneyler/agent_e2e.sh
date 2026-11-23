#!/usr/bin/env bash
# nefes-agent uçtan uca: gerçek bildirim sunucusu (xfce4-notifyd) ile.
# Pardus'ta, masaüstü kullanıcısı olarak:  bash deneyler/agent_e2e.sh
# Bildirim sunucusu trafiği dbus-monitor ile yakalanır (ekrana bakmadan doğrulama).
#  1) ajan açıkken: uygulama donar → bildirim; Resume → bildirim kapanır
#  2) ajan kapalıyken uygulama donar → ajan açılınca ListFrozen ile bildirim gelir
#  3) nefesd durur → tüm bildirimler kapanır
set -uo pipefail
cd "$(dirname "$0")/.."
export DISPLAY=:0
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"
BUS=tr.edu.bil461.Nefes1; OBJ=/tr/edu/bil461/Nefes1; IFACE=tr.edu.bil461.Nefes1.Manager
MON=$(mktemp /tmp/nefes-agent-monitor.XXXX)
AGENT_LOG=$(mktemp /tmp/nefes-agent-log.XXXX)
NEFES_LOG=$(mktemp /tmp/nefes-agent-nefesd.XXXX)
APP_SLICE="/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/app.slice"

cleanup() {
  for p in ${AGENT_PID:-} ${NEFES_PID:-} ${MON_PID:-} ${HOG_PID:-}; do kill "$p" 2>/dev/null; done
  for s in "$APP_SLICE"/app-nefes-python3-*.scope; do [ -d "$s" ] && echo 0 > "$s/cgroup.freeze"; done 2>/dev/null
  wait 2>/dev/null
}
trap cleanup EXIT
scope() { ls -d "$APP_SLICE"/app-nefes-python3-*.scope 2>/dev/null | head -1; }
frozen() { awk '/^frozen/{print $2}' "$(scope)/cgroup.events" 2>/dev/null || echo "-"; }
wait_frozen() { for _ in $(seq 40); do [ "$(frozen)" = "$1" ] && return 0; sleep 0.5; done; return 1; }
start_agent() { python3 -m nefes_agent >>"$AGENT_LOG" 2>&1 & AGENT_PID=$!; sleep 2; }
# zram açıkken 1100 MB gerçek baskı yaratmıyor (avg10 ~1, tetik gelmiyor) → 1500 MB
pressure() { stress-ng --vm 1 --vm-bytes 1500M --vm-keep --timeout "$1" --quiet & }

dbus-monitor --session "interface='org.freedesktop.Notifications'" >"$MON" 2>&1 &
MON_PID=$!

# Test uygulaması nefes-baslat ile kendi scope'unda (app-nefes-python3-*.scope)
bin/nefes-baslat python3 -c '
import mmap, os, time
n = 400 * 1024 * 1024
buf = mmap.mmap(-1, n, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)
page = os.urandom(1024) + bytes(3072)
for i in range(0, n, 4096): buf[i:i + 4096] = page
while True:  # her saniye sayfalara dokun: çözülünce bellek geri gelsin, tekrar aday olsun
    for i in range(0, n, 4096): buf[i] = (buf[i] + 1) & 0xFF
    time.sleep(1)
' &
HOG_PID=$!
sleep 6
SCOPE_PATH="$(scope)"; SCOPE_PATH="${SCOPE_PATH#/sys/fs/cgroup}"
echo "uygulama scope'u: $SCOPE_PATH"

start_agent
python3 -m nefesd --cooldown 1 >"$NEFES_LOG" 2>&1 &
NEFES_PID=$!
sleep 2

echo "== [1] ajan açıkken baskı"
pressure 12s; wait_frozen 1 && echo "    donduruldu"
sleep 1
echo "    Resume (Devam ettir düğmesinin yaptığı çağrı):"
gdbus call --session --dest $BUS --object-path $OBJ --method $IFACE.Resume "$SCOPE_PATH"
sleep 1
wait %?stress-ng 2>/dev/null; sleep 2

echo "== [2] ajan kapalıyken dondurma, sonra ajan açılır (ListFrozen eşitlemesi)"
kill "$AGENT_PID"; wait "$AGENT_PID" 2>/dev/null; AGENT_PID=""
pressure 12s; wait_frozen 1 && echo "    donduruldu (ajan kapalı)"
start_agent
sleep 1

echo "== [3] nefesd durur → bildirimler kapanmalı"
kill "$NEFES_PID"; wait "$NEFES_PID" 2>/dev/null; NEFES_PID=""
sleep 2
kill "$AGENT_PID"; wait "$AGENT_PID" 2>/dev/null; AGENT_PID=""

kill "$MON_PID"; MON_PID=""
echo; echo "== bildirim sunucusu trafiği (Notify başlıkları ve kapatmalar)"
grep -E 'string "[^"]*duraklatıldı"|member=CloseNotification' "$MON" \
  | sed -E 's/.*(string "[^"]*duraklatıldı").*/  Notify: \1/; s/.*member=(CloseNotification).*/  \1/'
echo; echo "== ajan günlüğü"; cat "$AGENT_LOG"
echo; echo "== nefesd günlüğü"; grep -E "DONDURULDU|DEVAM|D-Bus" "$NEFES_LOG"
