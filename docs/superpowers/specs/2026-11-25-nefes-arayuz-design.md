---
tags: [nefes, tasarim, arayuz]
durum: onaylandi
sorumlu: Gültekin
tarih: 2026-11-25
---
# Nefes arayüzü — panel simgesi + durum/ayar penceresi

## Amaç ve neden
Nefes bugün yalnızca terminalden yönetiliyor (`systemctl --user …`, `journalctl`, `gdbus call …`).
Hedef: **bir Pardus kullanıcısının günlük kullanacağı** sakin bir durum ve ayar aracı. Kullanıcı
terminal açmadan şunları yapabilmeli: Nefes'in çalıştığını ve bellek baskısını görmek, donuk
uygulamaları görüp devam ettirmek, son olaylara bakmak, birkaç anlaşılır ayarı değiştirmek.

## Hedefler
- Xfce panelinde **durum simgesi** (Ayatana AppIndicator): durumu gösterir, menüsünden donuk
  uygulamalar devam ettirilir, pencere açılır, Nefes duraklatılır.
- Tek **durum ve ayar penceresi** (GTK 3), uygulama menüsünden ve simge menüsünden açılır.
  Onaylanan taslak:
  ```
  ┌ Nefes ───────────────────────────────────────┐
  │ ● Nefes açık                    [Duraklat]   │
  │ Bellek baskısı  ▁▂▂▃▅▃▂▁  düşük              │
  │ RAM 1,4 / 2,0 GB   ·   zram 310 MB → 95 MB   │
  ├──────────────────────────────────────────────┤
  │ Dondurulan uygulamalar                       │
  │  Firefox    420 MB   3 dk   [Devam ettir]    │
  ├──────────────────────────────────────────────┤
  │ Son olaylar                                  │
  │  14:02 Firefox donduruldu (baskı yüksek)     │
  │  13:40 Calc devam ettirildi (sen)            │
  ├──────────────────────────────────────────────┤
  │ Ayarlar                                      │
  │  Hassasiyet       ○ Az  ● Orta  ○ Çok        │
  │  En uzun donma    [10 dk ▾]                  │
  │  Asla dondurma    VLC, Thunderbird  [+ Ekle] │
  │  Bildirim göster  [✓]                        │
  └──────────────────────────────────────────────┘
  ```
- Hiçbir işlem parola istemez (nefesd kullanıcı servisi; ayarlar `~/.config/nefes/`).
- Tüm metinler Türkçe.

## Hedef dışı
- GNOME desteği (simge için eklenti gerekir; ADR-0002 gereği ek işlev).
- Ham eşiklerin (ms, avg10) düzenlenmesi; zram boyutu ayarı (root ister); elle dondurma.
- Oturumlar arası olay geçmişi / grafik kaydı.

## Olmaması gerekenler (çalışsa bile başarısızlık sayılır)
- Pencere ya da simge **dondurulabilir** olursa (ajan korunan listede ve `session.slice`'ta kalmalı).
- Pencere kapalıyken **sürekli yoklama** (M5: boşta CPU ≈ 0). Gösterge güncellemesi yalnızca
  pencere görünürken yapılır; simge yalnızca sinyallerle güncellenir.
- Bozuk/eksik ayar dosyası nefesd'yi düşürürse ya da korunan listeyi zayıflatırsa. Kullanıcının
  "asla dondurma" listesi yalnızca **ekler**; yerleşik korunan liste kaldırılamaz.
- Ayatana yoksa ajanın bildirim işlevi bozulursa (simge olmadan da çalışmalı).

## Kısıtlar
- Python 3.13 + PyGObject (Gtk 3, Gio, GLib, Notify, AyatanaAppIndicator3); yeni PyPI bağımlılığı yok.
  `gir1.2-ayatanaappindicator3-0.1` Pardus 25'te kurulu (25 Kas doğrulandı).
- D-Bus sözleşmesi tek yetkili kaynak (`nefesd/tr.edu.bil461.Nefes1.xml`, ADR-0003): önce XML,
  sonra kod. Değişiklikler **yalnızca ekleme**; mevcut üye ve anlamlar değişmez.
- Ajan nefesd kodunu içe aktarmaz (yalnızca XML'i yükler). Ortak ayar kodu ayrı pakette.
- Karar motoru saf kalır; ayarlar `Policy`/`Config` alanlarına çevrilerek verilir.

## Yaklaşımlar
**Simge:** (A) Ayatana AppIndicator — standart StatusNotifier, Pardus'ta kurulu, sol tık menü açar.
(B) Gtk.StatusIcon — bağımlılıksız, sol tık pencereyi açar; ama deprecated, HiDPI'da bulanık.
→ **A seçildi** (kullanıcı, 25 Kas).

**Süreç:** (1) nefes-agent'ın içinde — tek Python+GTK süreci; ajan zaten korunuyor ve sinyalleri
dinliyor. (2) Ayrı `nefes-panel` — temiz ayrım ama ikinci ~25–30 MB GTK süreci.
→ **1 seçildi** (kullanıcı, 25 Kas).

## Tasarım

### Bileşenler
| Parça | Yer | Görev |
|---|---|---|
| `nefes_ayar/` (yeni, saf) | ortak | Ayar dosyasını okur/doğrular/yazar; kademe → sayı eşlemesi |
| nefesd | `nefesd/` | Ayarları açılışta ve `ReloadSettings`'te uygular; duraklatma; olay halkası; baskı seviyesi sinyali |
| nefes-agent | `nefes_agent/` | `Gtk.Application` olur: bildirimler (bugünkü gibi) + simge + pencere |
| Menü kaydı | `data/applications/nefes.desktop` | `nefes-agent --pencere` → çalışan örneğin penceresini öne getirir |

### Ayar dosyası — `~/.config/nefes/ayarlar.ini` (`$XDG_CONFIG_HOME`)
```ini
[nefes]
etkin = true                 ; false = duraklatıldı
hassasiyet = orta            ; az | orta | cok
en_uzun_donma_dk = 10        ; 5 | 10 | 20 | 30
asla_dondurma = vlc, thunderbird
bildirim = true              ; yalnızca ajan okur
```
- Eşleme (Claude'un önerisi): hassasiyet az/orta/çok → PSI `stall-ms` 500 / 300 / 200
  (150 ms kısa ayırma dalgalarında yanlış tetikledi, Deney 03). Varsayılanlar bugünkü komut
  satırı varsayılanlarıyla aynı: orta (300 ms), 10 dk.
- Dosya yoksa varsayılanlar. Bozuk alan → o alan varsayılan + günlüğe uyarı; dosyanın tamamı
  okunamazsa tüm varsayılanlar. nefesd hiçbir ayar hatasında düşmez.
- Yazma atomik (geçici dosya + `os.replace`). **Dosyaya yalnızca ajan yazar** (tek yazar → kayıp
  güncelleme yok); nefesd yalnızca okur. (Claude'un kararı.)
- `asla_dondurma` öğeleri, `nefes-baslat`'ın scope adında kullandığı program adıyla aynı biçimde
  normalleştirilir (`unit_name` kuralı: küçük harf, `[a-z0-9-]`). "+ Ekle" menüdeki uygulamaları
  (`menu_apps`) listeler; seçilen kaydın `Exec` programından ad türetilir. Eşleştirme
  `karar.py`'deki gibi scope adında alt dize — yerleşik korunan listeyle aynı kural.
- Komut satırı seçenekleri (`--stall-ms`, `--max-frozen`) açıkça verilirse dosyadan **önceliklidir**
  (ölçüm betikleri bozulmasın).

### D-Bus sözleşmesine eklemeler (`tr.edu.bil461.Nefes1.Manager`)
| Üye | İmza | Anlam |
|---|---|---|
| `GetStatus()` | `→ (b enabled, s pressure_level, d some_avg10)` | Anlık durum; pencere görünürken 2 s'de bir çağrılır |
| `SetEnabled(b)` | `→ ()` | Duraklat/sürdür (anında). `false`: yeni dondurma yok, donuk her şey `reason="paused"` ile çözülür. Kalıcılık için ajan önce `etkin` alanını dosyaya yazar, sonra bunu çağırır; nefesd açılışta dosyadan okur |
| `ReloadSettings()` | `→ (b ok, s message)` | Dosyayı yeniden okur; geçersizse eski ayarlar kalır, `message` Türkçe neden |
| `RecentEvents()` | `→ a(tsss)` | (unix zamanı, "frozen"/"resumed", app_name, reason) — son 20 olay, en yeni sonda |
| `StatusChanged` sinyali | `(b enabled, s pressure_level)` | Etkinlik ya da baskı **seviyesi** değişince (her PSI okumasında değil) |
- `pressure_level`: `psi.classify` çıktısı — `"safe"` (pencerede "düşük") | `"normal"` ("orta") | `"high"` ("yüksek").
- `AppResumed.reason` için yeni değer: `"paused"` (sözleşme bilinmeyen değeri zaten kabul ediyor).
- Karar kaydı: **ADR-0004 Arayüz ve sözleşme genişletmesi**.

### nefesd değişiklikleri
- Açılışta ayarları okur; `ReloadSettings`'te `Policy`/`Config`'i yeniden kurar. `stall-ms`
  değişirse PSI tetikleyicisi kapatılıp yeniden açılır (ana döngüde, kilit altında).
- Duraklatılmışken `tick` dondurma kararı üretmez; güvenlik zamanlayıcıları ve kapanışta çözme aynen sürer.
- Olay halkası: `deque(maxlen=20)`, `notify` dinleyicisi olarak eklenir.

### nefes-agent değişiklikleri
- `Gtk.Application(application_id="tr.edu.bil461.NefesAgent")`: ikinci başlatma (`--pencere`)
  çalışan örneğe `activate` gönderir → pencere öne gelir. Pencere kapatılınca gizlenir, süreç sürer.
- **Simge** (Ayatana): durum ve metin saf bir fonksiyondan gelir:
  `tray_state(service_up, enabled, level, frozen_count) → (simge_adı, ipucu)` —
  çalışmıyor / duraklatıldı / normal / baskı var / uygulama donuk.
  Simgeler paketle gelen SVG'ler (`/usr/share/icons/hicolor/scalable/status/nefes-*.svg`).
  Menü: durum satırı (pasif) · her donuk uygulama için "Ad (3 dk) — Devam ettir" · "Nefes'i aç…" · "Duraklat"/"Sürdür".
- **Pencere**: bölümler taslaktaki sırayla. Görünürken 2 s'lik `GLib.timeout` ile `GetStatus` +
  `/proc/meminfo` + `/sys/block/zram0/mm_stat` okur (root gerekmez); gizliyken zamanlayıcı durur.
  Baskı çizgisi son 60 örneği bellekte tutar. Ayar değişikliği → dosyaya yaz → `ReloadSettings`;
  `ok=false` ise değişiklik geri alınır ve mesaj pencerede gösterilir.
- `bildirim=false` ise bildirim gösterilmez; simge ve pencere çalışmaya devam eder.
- Ayatana içe aktarılamazsa simge atlanır, günlüğe uyarı; bildirim + pencere çalışır.
- nefesd yoksa: simge "Nefes çalışmıyor" gösterir, pencerede düğmeler pasif.
- Menüden `--pencere` ile açıldığında çalışan ajan yoksa bu süreç tam ajan olarak çalışır
  (`nefes` öneki `nefes-baslat` dışında → session scope'ta, dondurulmaz).

### Test
- TDD; saf mantık macOS'ta da çalışacak biçimde: `nefes_ayar` (okuma/doğrulama/eşleme/atomik yazma),
  `tray_state`, pencere metin biçimlendirme (MB, "3 dk", olay satırı), olay halkası, `SetEnabled`
  (duraklatınca çözme + yeni dondurma yok), `ReloadSettings` (geçersizde eski ayar), komut satırı önceliği.
- Sözleşme: `Gio.TestDBus` ile yeni metot/sinyal testleri (mevcut `test_dbus_servis` düzeni).
- GTK/Ayatana kodu ince tutulur; Pardus VM'de elle doğrulanır (ekran görüntüsüyle).
- M5'i yeniden ölç: nefesd CPU/RSS değişmemeli; ajanın RSS'i ayrıca not edilir.

### Paketleme
- `debian/control`: `gir1.2-gtk-3.0` Depends; `gir1.2-ayatanaappindicator3-0.1` Recommends
  (simgesiz de çalışır).
- `nefes.desktop` menü kaydı ve SVG simgeleri `nefes.install`'a; sürüm 0.6.0.

## Builder'a bırakılanlar
- Pencerenin tam yerleşimi, boşluklar, GTK widget seçimi (taslak bağlayıcıdır, piksel değil).
- Simge çizimleri (5 durum, sade).
- Olay satırlarındaki neden metinleri ("baskı yüksek", "sen", "odaklandın", "süre doldu",
  "baskı azaldı", "duraklatıldı").
- `GetStatus` yoklama aralığı (≥ 1 s).
