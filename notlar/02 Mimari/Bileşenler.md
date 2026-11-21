---
tags: [nefes, mimari]
---
# Bileşenler

![[Mimari.canvas]]

| Bileşen | Nerede | Görev | Sorumlu |
|---|---|---|---|
| **nefesd** | systemd sistem servisi (root) | [[PSI]] tetikleyicisini dinler, `app.slice` scope'larını tarar, [[Karar Motoru]] ile aday seçer, dondurur, geri kazanır, devam ettirir; olayları D-Bus sistem veriyolunda yayınlar | G |
| **nefes-agent** | kullanıcı oturumu (autostart) | olayları Türkçe bildirime çevirir; "Devam ettir" → servis; **X11 odak izleme** (`_NET_ACTIVE_WINDOW` → PID → cgroup) → servis | A |
| **nefes-baslat** | kullanıcı oturumu | uygulamaları `systemd-run --user --scope` ile `app.slice` altında kendi scope'unda başlatır; `.desktop` geçersiz kılmaları | A |
| ~~GNOME Shell eklentisi~~ | — | ek işleve indi → [[ADR-0002 Asgari ürün Xfce]] | — |
| **nefes-zram** | kurulum + ilk açılış | RAM'e göre `zram-generator.conf` yazar ([[zram]]) | G |
| **nefes-olcum** | test ortamı | gecikme probu, PSI kaydedici, yük senaryoları → CSV, grafik | A |
| nefes-ayarlar (ek) | kullanıcı oturumu | eşikler, korunan liste, olay geçmişi (GTK) | A |

## Çalışma akışı
1. Açılışta `/proc/pressure/memory`'ye tetikleyici yaz (örn. `some 150000 1000000`), `poll()` ile bekle — baskı yokken CPU ≈ 0.
2. Tetik gelince `user@UID.service/app.slice/*.scope` listele, her biri için `memory.current` oku.
3. Korunan + odaktakini ele; en büyüğü seç.
4. `cgroup.freeze ← 1`, `cgroup.events` içinde `frozen 1` doğrula, sonra `memory.reclaim` yaz.
5. D-Bus'ta yayınla → ajan bildirir.
6. Baskı sürerse sonraki aday; yetmezse Seviye 3.
7. "Devam ettir" veya baskı düştü → `cgroup.freeze ← 0`. Güvenlik zamanlayıcısı azami süreyi sınırlar.

## Modül durumu (2026-11-21)
| Modül | Durum | Test |
|---|---|---|
| `karar.py` | ✅ yazıldı | 35 birim |
| `cgroups.py` | ✅ yazıldı — `read_apps`, `list_frozen`, `cgroup_of_pid`, `freeze`, `thaw`, `reclaim`; yazma yolu dir_fd + `O_NOFOLLOW` (kontrol-yazma yarışı yok), kapanan uygulama → `ScopeGone` | 47 birim (cgroups + psi, sahte ağaç) + 6 VM entegrasyon |
| `psi.py` | ✅ kısmen — `parse_pressure` (bozuk girdide ValueError), `trigger_line`, `classify`; `poll` döngüsü daemon'da | (yukarıda) |
| `eylem.py` | ✅ `Daemon` çekirdeği — durum, monoton saat, zaman aşımı/güvenli kontrol zamanlayıcısı, cooldown, açılışta/kapanışta çözme, kullanıcı "Devam ettir" | 13 birim (sahte saat) |
| `focus.py` | ✅ X11 odak (`_NET_ACTIVE_WINDOW` → PID → cgroup); okunamazsa "bilinmiyor" | uçtan uca |
| `__main__.py` | ✅ `python3 -m nefesd` — PSI poll döngüsü, SIGTERM'de çözme | uçtan uca ([[Deney 03 Uçtan Uca nefesd]]) |
| `dbus_servis.py` | ⏳ | — |

VM entegrasyon testleri: `NEFES_VM=1 python3 -m pytest -q tests/test_vm.py` (Pardus'ta, root gerekmez; kendi `app-nefes-test-*` scope'unu açıp kapatır). 2026-11-21: 6/6 geçti.

## Modül sınırları (nefesd)
- `psi.py` — tetikleyici kurma, `poll` döngüsü, `/proc/pressure/memory` okuma
- `cgroups.py` — keşif ve anlık görüntü (salt okuma) + yazma işlemleri (freeze/reclaim/high) — **tek dosya sistemi sınırı**
- `karar.py` — saf karar fonksiyonu → [[Karar Motoru]]
- `eylem.py` — eylem sırası, zamanlayıcılar, durum makinesi
- `dbus_servis.py` — [[D-Bus Sözleşmesi]] uygulaması (Gio)
