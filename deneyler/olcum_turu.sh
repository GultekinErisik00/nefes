#!/usr/bin/env bash
# Hafta 7 ölçüm turu: 3 yapılandırma × N tekrar, sırayla (sapmayı azaltmak için iç içe).
#   sudo bash deneyler/olcum_turu.sh [TEKRAR=5]
#   varsayilan : zram KAPALI (yalnız disk swap), earlyoom kapalı, nefesd kapalı  → öneri: "varsayılan Pardus"
#   earlyoom   : zram KAPALI, earlyoom AÇIK, nefesd kapalı
#   nefes      : zram AÇIK, earlyoom kapalı, nefesd + nefes-agent AÇIK
# Her çalıştırmadan önce: disk swap boşaltılır, sayfa önbelleği atılır. Sonunda makine "nefes"
# yapılandırmasına döner. Ölçüm kullanıcı olarak (deneyler/olcum_senaryo.sh) yapılır.
set -uo pipefail
[ "$(id -u)" -eq 0 ] || { echo "root olarak çalıştırın: sudo bash $0"; exit 1; }
cd "$(dirname "$0")/.."
N=${1:-5}
U=${SUDO_USER:-user}; UID_U=$(id -u "$U")
OUT="olcumler/tur-$(date +%Y%m%d-%H%M)"
RUNAS=(sudo -u "$U" env DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/$UID_U
       DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$UID_U/bus)
DISK_SWAP=$(awk '$2=="partition" && $1 !~ /zram/ {print $1; exit}' /proc/swaps)
log() { echo "[$(date +%H:%M:%S)] $*"; }

# Ölçülen kod = depodaki kod: paketi bu klasörden yeniden derleyip kur.
log "paket derleniyor ve kuruluyor (güncel kod)"
find . -name "._*" -delete
sudo -u "$U" dpkg-buildpackage -us -uc -b >/dev/null 2>&1 && dpkg -i ../nefes_*_all.deb >/dev/null \
  || { echo "paket derlenemedi/kurulamadı"; exit 1; }
log "kurulu: $(dpkg-query -W -f='nefes ${Version}' nefes), mean_sd: $(grep -c mean_sd /usr/lib/python3/dist-packages/nefes_olcum/__init__.py)"
dpkg -s earlyoom >/dev/null 2>&1 || apt-get install -y -q earlyoom >/dev/null
systemctl disable --now earlyoom >/dev/null 2>&1

# zram swap'ı systemd'nin dev-zram0.swap birimi yönetir; start/stop eşzamanlıdır. (1. turda
# `restart systemd-zram-setup@` + `swapoff` kullanılmıştı: swap gecikmeli açılıp bir sonraki
# yapılandırmaya kaydı — 2026-11-23, Deney 05 çalıştırma 1 geçersiz.)
# 2. tur (25 Kas): `stop dev-zram0.swap` da yetmedi — `systemctl start earlyoom` sysinit.target →
# swap.target bağımlılıklarını yeniden işletip zram'ı tekrar açtı (verify yakaladı). Kapalıyken birim
# geçici (--runtime) maskelenir: hiçbir şey başlatamaz; çıkışta maske her durumda kaldırılır.
# 3. deneme (25 Kas): runtime mask da zram'ı kapatamadı ("dependency job for dev-zram0.swap
# failed") → systemd birimi devreden çıkarıldı: cihaz açılışta kurulu, swap doğrudan
# swapon/swapoff ile; kapatma her zaman systemctl start'lardan SONRA yapılır (configure).
zram() {
  if [ "$1" = on ]; then
    grep -q '^/dev/zram0 ' /proc/swaps || swapon -p 100 /dev/zram0
  else
    swapoff /dev/zram0 2>/dev/null || true
  fi
}
trap 'zram on' EXIT
zram_active() { grep -q '^/dev/zram0 ' /proc/swaps; }
earlyoom_active() { systemctl is-active --quiet earlyoom; }
nefesd_active() { "${RUNAS[@]}" systemctl --user is-active --quiet nefesd.service; }
verify() {  # beklenen durum değilse çalıştırma YAPILMAZ
  local want_z=no want_e=no want_n=no z=no e=no n=no
  case "$1" in earlyoom) want_e=yes ;; nefes) want_z=yes; want_n=yes ;; esac
  zram_active && z=yes; earlyoom_active && e=yes; nefesd_active && n=yes
  if [ "$z$e$n" != "$want_z$want_e$want_n" ]; then
    log "HATA: $1 için beklenen zram=$want_z earlyoom=$want_e nefesd=$want_n, olan zram=$z earlyoom=$e nefesd=$n"
    return 1
  fi
}
nefes_user() { "${RUNAS[@]}" systemctl --user "$1" nefesd.service nefes-agent.service 2>/dev/null || true; }
configure() {
  case "$1" in
    varsayilan) nefes_user stop; systemctl stop earlyoom; zram off ;;
    earlyoom)   nefes_user stop; systemctl start earlyoom; zram off ;;  # start, zram'ı geri açabilir
    nefes)      systemctl stop earlyoom; zram on; nefes_user start ;;
  esac
}
reset_memory() {
  [ -n "$DISK_SWAP" ] && { swapoff "$DISK_SWAP" && swapon "$DISK_SWAP"; }
  sync; echo 3 > /proc/sys/vm/drop_caches
  sleep 5
}

"${RUNAS[@]}" mkdir -p "$OUT"
log "tur başlıyor: $N tekrar × 3 yapılandırma → $OUT (disk swap: ${DISK_SWAP:-yok})"
for n in $(seq "$N"); do
  for cfg in varsayilan earlyoom nefes; do
    configure "$cfg"; reset_memory
    verify "$cfg" || { configure nefes; exit 1; }
    log "tekrar $n/$N: $cfg  (swap: $(awk 'NR>1{printf "%s ", $1}' /proc/swaps)| earlyoom: $(systemctl is-active earlyoom) | nefesd: $("${RUNAS[@]}" systemctl --user is-active nefesd))"
    "${RUNAS[@]}" bash deneyler/olcum_senaryo.sh "$OUT/$cfg-$n"
    log "   $(cat "$OUT/$cfg-$n/notlar.txt" 2>/dev/null)"
  done
done

configure nefes
systemctl disable earlyoom >/dev/null 2>&1
log "tur bitti; makine 'nefes' yapılandırmasında (zram açık, nefesd açık, earlyoom kapalı)"
echo
"${RUNAS[@]}" nefes-olcum ozet "$OUT"/varsayilan-[0-9]*/ "$OUT"/earlyoom-[0-9]*/ "$OUT"/nefes-[0-9]*/ | tee "$OUT/ozet.txt"
