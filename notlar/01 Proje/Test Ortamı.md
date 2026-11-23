---
tags: [nefes, ortam]
makine: userpardus
tarih: 2026-11-21
---
# Test Ortamı — `userpardus`

Bağlantı: `ssh userpardus` (macOS `~/.ssh/config` kaydı). Kullanıcı `user` (uid 1000), sudo grubunda, **sudo parola istiyor**.

## Hafta 1 durum notu (2026-11-21 ölçümü)
| Konu | Değer | Öneriyle karşılaştırma |
|---|---|---|
| Dağıtım | Pardus 25.2 (yirmibeş) | ✅ |
| Çekirdek | 6.12.95+deb13-amd64 | ✅ (≥ 5.19) |
| systemd | 257.13 | ✅ |
| Sanallaştırma | VirtualBox (`oracle`) | ✅ |
| CPU / RAM | **1 vCPU / 2 GB** (1973 MB) | ⚠️ test düzeni 2 vCPU / 4 GB diyor |
| Masaüstü | **Xfce, X11** (`xfce4-session`, `xfwm4`) | ⚠️ asgari ürün GNOME varsayıyordu |
| Swap | `/dev/sda5` disk bölümü, 1.1 GB, öncelik -2 | zram **yok** → **23 Kas: zram kuruldu** (`systemd-zram-generator` + `nefes_zram`: 1973 MB zstd, öncelik 100) |
| vm.swappiness | 60 | — |
| earlyoom / systemd-oomd / nohang / zram-generator | hiçbiri kurulu değil | varsayılan Pardus = yalnız çekirdek OOM |
| PSI | `/proc/pressure/memory` çalışıyor | ✅ |
| cgroup | v2 (`cgroup2fs`), denetleyiciler: cpuset cpu io memory hugetlb pids rdma misc | ✅ |
| Python / PyGObject | 3.13.5 / gi 3.50.0 | ✅ |
| git, pytest, stress-ng | **kurulu değil** | kurulacak |
| Disk | 19 GB, 13 GB boş | ✅ |

## cgroup ağacı — kritik bulgu
```
user.slice/user-1000.slice/
  session-2.scope          ← xfwm4, xfce4-panel, xfdesktop, Thunar ... HEPSİ BURADA
  user@1000.service/
    app.slice/             ← yalnızca dbus, dconf, evolution, gpg-agent gibi servisler
    session.slice/         ← pipewire, wireplumber, gvfs, at-spi
```
- Xfce, uygulamaları **ayrı scope'larda başlatmıyor**: masaüstünden açılan her şey pencere yöneticisi ve panelle aynı `session-2.scope` içinde. O scope'u dondurmak = masaüstünü dondurmak. → [[Riskler]]
- Çözüm yolu (öneride "ek işlev" olarak vardı): uygulamaları `systemd-run --user --scope --unit=app-nefes-<ad>-<pid>` ile başlatan sarmalayıcı (.desktop `Exec=` satırları veya panel başlatıcısı).
- Odak bilgisi X11'de kolay: `_NET_ACTIVE_WINDOW` + `_NET_WM_PID` — GNOME Shell eklentisine gerek yok.

## Yetki bulgusu
`user@1000.service` altı kullanıcıya **devredilmiş** (delegation): `app.slice/cgroup.freeze` ve `memory.reclaim` sahibi `user`. Yani kullanıcı kendi uygulama cgroup'larını root olmadan dondurabilir / geri kazanabilir. Prototip aşamasında root gerekmez; nihai tasarımda nefesd'nin root mu yoksa kullanıcı servisi mi olacağı → [[Kararlar]].

## Yapılacaklar
- [ ] VirtualBox'ta RAM 4 GB, 2 vCPU (test düzenine uyum) — veya 2 GB'ı "zor senaryo" olarak ayrıca tut
- [ ] `sudo apt install git python3-pytest stress-ng` (kullanıcı kendisi çalıştırmalı — parola)
- [ ] Ajanın sudo gerektiren işleri için: ya kullanıcı komutları kendisi çalıştırır, ya da yalnızca geliştirme VM'inde dar kapsamlı `NOPASSWD` kuralı
- [ ] GNOME mu Xfce mi? → [[Kararlar]]
