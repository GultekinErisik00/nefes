---
tags: [nefes, cekirdek]
kaynak: https://docs.kernel.org/admin-guide/cgroup-v2.html
---
# cgroup v2

## GNOME'da uygulamalar nerede?
GNOME (40+) her uygulamayı ayrı bir systemd scope'unda başlatır:
```
/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/
    app-gnome-firefox_firefox-4321.scope/
    app-gnome-org.gnome.Nautilus-5678.scope/
    app-org.gnome.Terminal.slice/ ...
/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/session.slice/
    org.gnome.Shell@wayland.service   ← KORUNAN (zaten app.slice dışında)
```
- Bir PID'in cgroup'u: `cat /proc/<pid>/cgroup` → `0::/user.slice/.../app-gnome-firefox-4321.scope`
- [ ] Pardus 25'te gerçek ağaç yapısını `systemd-cgls --user-unit` ile doğrula ve buraya yapıştır.

## Kullanılan arayüz dosyaları
| Dosya | Okuma/Yazma | Anlam |
|---|---|---|
| `memory.current` | R | cgroup'un şu anki bellek kullanımı (bayt) |
| `memory.stat` | R | `anon`, `file`, `shmem`… ayrımı |
| `memory.swap.current` | R | swap'taki miktar (reclaim sonrası artmalı) |
| `memory.high` | W | yumuşak sınır — aşınca kısma + geri kazanım (Seviye 1) |
| `memory.reclaim` | W | → [[memory.reclaim]] |
| `memory.pressure` | R/W | cgroup başına [[PSI]] |
| `cgroup.freeze` | W | `1` dondur, `0` çöz (5.2+) |
| `cgroup.events` | R | `populated 0/1`, `frozen 0/1` — dondurma **asenkron**, buradan doğrula (inotify/poll ile `POLLPRI` değişim bildirir) |

## cgroup.freeze
- Alt ağaçtaki tüm süreçler durdurulur; SIGSTOP'tan farklı olarak süreç bunu göremez/engelleyemez, ebeveyn `wait` ile fark etmez.
- Donmuş süreçlerin belleği **boşalmaz** → bu yüzden ardından reclaim gerekir.
- Donmuş cgroup'a yeni süreç girerse o da donar.
- Yazma yetkisi: root (nefesd).

İlgili: [[Karar Motoru]], [[zram]]
