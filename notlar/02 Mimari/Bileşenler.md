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
| `eylem.py` | ✅ `Daemon` çekirdeği — durum, monoton saat, zaman aşımı/güvenli kontrol zamanlayıcısı, cooldown, açılışta/kapanışta çözme, kullanıcı "Devam ettir", hata yolları, **reclaim arka planda** (`run_async`) | 22 birim (sahte saat, ertelenmiş iş) |
| `focus.py` | ✅ X11 odak (`_NET_ACTIVE_WINDOW` → PID → cgroup); okunamazsa "bilinmiyor" | uçtan uca |
| `__main__.py` | ✅ `python3 -m nefesd` — PSI poll döngüsü, SIGTERM'de çözme | uçtan uca ([[Deney 03 Uçtan Uca nefesd]]) |
| `dbus_servis.py` | ✅ oturum veriyolu `tr.edu.bil461.Nefes1`; `Resume`, `ListFrozen`, `AppFrozen`, `AppResumed`; sözleşme XML'den yüklenir ([[ADR-0003 D-Bus sözleşmesi]]); ayrı GLib iş parçacığı, Daemon kilitli vekil (`Locked`) | 22 birim (XML'e karşı sözleşme testi + `Gio.TestDBus`) + gerçek veriyolunda `dbus_e2e.sh` — sinyal sırası hatası bulundu ve düzeltildi ([[D-Bus Sözleşmesi]]) |
| `nefes_agent/` | ✅ oturum ajanı: `AppFrozen` → kalıcı Türkçe bildirim "Firefox duraklatıldı … [Devam ettir]" (libnotify, xfce4-notifyd); düğme → `Resume`; `AppResumed` → bildirim kapanır; nefesd görününce `ListFrozen` ile eşitlenir, kaybolunca hepsini kapatır. Sözleşmeyi yalnızca XML'den alır (`Gio.DBusProxy` + arayüz bilgisi) | 13 birim (saf mantık) + `deneyler/agent_e2e.sh` (gerçek bildirim sunucusu, 3 senaryo) |
| `nefes_baslat/` + `bin/nefes-baslat` | ✅ uygulamayı `systemd-run --user --scope --unit=app-nefes-<ad>-<rastgele>` ile kendi scope'unda başlatır; kullanıcı yöneticisi yoksa doğrudan çalıştırır (uygulama her durumda açılır); `--desktop-install` menü/panel `.desktop` kopyalarını sarmalar (kullanıcının kendi kopyasına dokunmaz, `DBusActivatable=false`), `--desktop-remove` geri alır | 23 birim + Pardus'ta: Firefox ve menüden (`gtk-launch`) açılan Calc kendi scope'unda |
| `debian/` + `data/` (paket) | ✅ `nefes_0.5.0_all.deb`: `/usr/bin` komutları, systemd kullanıcı birimleri (`Slice=session.slice` → kendileri aday değil; nefesd `ExecStopPost=--thaw-all`, `Restart=on-failure`), XDG autostart → `nefes-oturum`, D-Bus arayüzü `/usr/share/dbus-1/interfaces/`, postinst zram yazar, postrm purge'de yalnızca kendi zram dosyasını siler | Pardus'ta derlendi + kuruldu; `nefes-oturum` ile servisler aktif; **SIGKILL sonrası ExecStopPost donuk uygulamayı çözdü, systemd yeniden başlattı** (23 Kas) |
| `nefes_olcum/` | ✅ `kaydet`: 100 ms GLib zamanlayıcı gecikme probu + 1 s PSI kaydı → `prob.csv`, `psi.csv`; `ozet`: M1 (p99, maks), M2 (>1 s gecikmelerin toplamı), PSI tepe; `deneyler/olcum_karsilastirma.sh` Nefes kapalı/açık | 12 birim + [[Deney 04 Ölçüm Önizlemesi]] |
| `nefes_zram/` | ✅ RAM → `zram-generator.conf` (kademeli boyut/algoritma, atomik yazma, yöneticinin dosyasını korur); `python3 -m nefes_zram` | 28 birim |

VM entegrasyon testleri: `NEFES_VM=1 python3 -m pytest -q tests/test_vm.py` (Pardus'ta, root gerekmez; kendi `app-nefes-test-*` scope'unu açıp kapatır). 2026-11-21: 6/6 geçti.

## Modül sınırları (nefesd)
- `psi.py` — tetikleyici kurma, `poll` döngüsü, `/proc/pressure/memory` okuma
- `cgroups.py` — keşif ve anlık görüntü (salt okuma) + yazma işlemleri (freeze/reclaim/high) — **tek dosya sistemi sınırı**
- `karar.py` — saf karar fonksiyonu → [[Karar Motoru]]
- `eylem.py` — eylem sırası, zamanlayıcılar, durum makinesi
- `dbus_servis.py` — [[D-Bus Sözleşmesi]] uygulaması (Gio)
