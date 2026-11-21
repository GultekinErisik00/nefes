#!/usr/bin/env bash
# Nefes spike: scope -> freeze -> memory.reclaim -> thaw, measured.
# Runs as the unprivileged user; touches only a scope it creates itself.
# Usage (from macOS): ssh userpardus 'bash -s' < deneyler/freeze_spike.sh [MB]
set -euo pipefail
MB=${1:-400}
UNIT="app-nefes-spike-$$"
APP="/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/app.slice/${UNIT}.scope"
LOG=$(mktemp /tmp/nefes-spike.XXXX)

cleanup() { [ -d "$APP" ] && echo 0 > "$APP/cgroup.freeze" 2>/dev/null; systemctl --user stop "${UNIT}.scope" 2>/dev/null || true; }
trap cleanup EXIT

# Worker: allocate MB of anon memory, then every 0.5 s touch every page and log how long it took.
WORKER='
import mmap, os, sys, time
n = int(sys.argv[1]) * 1024 * 1024
buf = mmap.mmap(-1, n, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)  # private anon, like a browser heap
# ~25% random bytes per page -> roughly 3-4:1 compressible, closer to real heaps than all-zero pages
pages = [os.urandom(1024) + bytes(3072) for _ in range(256)]
for k, i in enumerate(range(0, n, 4096)): buf[i:i + 4096] = pages[k % 256]
log = open(sys.argv[2], "a", buffering=1)
log.write(f"READY {time.monotonic():.3f}\n")
while True:
    t0 = time.monotonic()
    for i in range(0, n, 4096): buf[i] = (buf[i] + 1) & 0xFF
    t1 = time.monotonic()
    log.write(f"TOUCH {t1:.3f} {(t1 - t0) * 1000:.1f}ms\n")
    time.sleep(0.5)
'
systemd-run --user --scope --quiet --unit="$UNIT" python3 -c "$WORKER" "$MB" "$LOG" &
for _ in $(seq 60); do grep -q READY "$LOG" 2>/dev/null && break; sleep 0.5; done
sleep 1.5

ms_since() { python3 -c "import sys,time; print(int((time.time()-float(sys.argv[1]))*1000))" "$1"; }
mem()  { printf 'current=%5d MB  swap=%5d MB  anon=%5d MB' \
           $(( $(cat "$APP/memory.current") / 1048576 )) \
           $(( $(cat "$APP/memory.swap.current") / 1048576 )) \
           $(( $(awk '/^anon /{print $2}' "$APP/memory.stat") / 1048576 )); }
frozen() { awk '/^frozen/{print $2}' "$APP/cgroup.events"; }
now() { date +%s.%N; }

echo "scope:  $APP"
echo "pids:   $(tr '\n' ' ' < "$APP/cgroup.procs")"
echo "[0] baseline        $(mem)  frozen=$(frozen)"
echo "    last touch:     $(grep TOUCH "$LOG" | tail -1)"

t=$(now); echo 1 > "$APP/cgroup.freeze"
while [ "$(frozen)" != 1 ]; do sleep 0.01; done
echo "[1] frozen in $(ms_since "$t") ms  $(mem)  frozen=$(frozen)"
n_before=$(grep -c TOUCH "$LOG"); sleep 2; n_after=$(grep -c TOUCH "$LOG")
echo "    touches during 2 s frozen: $((n_after - n_before))  (expect 0)"
echo "    task state: $(awk '{print $3}' /proc/$(head -1 "$APP/cgroup.procs")/stat)"

t=$(now)
if echo "$(( MB * 1048576 ))" > "$APP/memory.reclaim" 2>/tmp/nefes-reclaim.err; then rc=ok; else rc="partial ($(cat /tmp/nefes-reclaim.err))"; fi
echo "[2] reclaim ${MB}M: $rc in $(ms_since "$t") ms  $(mem)"

t=$(now); echo 0 > "$APP/cgroup.freeze"
while [ "$(frozen)" != 0 ]; do sleep 0.01; done
echo "[3] thawed in $(ms_since "$t") ms"
for _ in $(seq 1200); do [ "$(grep -c TOUCH "$LOG")" -gt "$n_after" ] && break; sleep 0.1; done
echo "    first full pass after thaw done $(ms_since "$t") ms after thaw (= resume latency, M4)"
sleep 2
echo "    touches after thaw:"
grep TOUCH "$LOG" | tail -n +$((n_after + 1)) | head -4 | sed 's/^/      /'
echo "[4] after thaw      $(mem)"
echo "psi: $(head -1 /proc/pressure/memory)"
