---
tags: [nefes, karar, dbus, arayuz]
durum: kabul
tarih: 2026-11-25
sorumlu: Gültekin
---
# ADR-0004 — Arayüz: panel simgesi + pencere nefes-agent içinde, sözleşmeye yalnızca ekleme

## Bağlam
Nefes yalnızca terminalden yönetiliyordu (`systemctl`, `journalctl`, `gdbus`). Hedef, bir Pardus
kullanıcısının **günlük kullanacağı** durum ve ayar aracı: panelde simge, menüden açılan tek pencere.
Ayrıntılı tasarım: `docs/superpowers/specs/2026-11-25-nefes-arayuz-design.md`.
[[ADR-0003 D-Bus sözleşmesi]] `GetStatus`'u "ihtiyaç doğunca eklenerek gelir" diye ertelemişti.

## Karar
- **Simge:** Ayatana AppIndicator (StatusNotifier). Pardus 25'te `gir1.2-ayatanaappindicator3-0.1` kurulu.
- **Süreç:** simge ve pencere **nefes-agent'ın içinde** (`Gtk.Application`, tek örnek). Ajan korunan
  listede ve `session.slice`'ta → arayüz asla dondurulmaz; ikinci bir GTK süreci (~25–30 MB) yok.
- **Ayarlar:** `~/.config/nefes/ayarlar.ini` (`nefes_ayar` paketi). **Tek yazar: ajan**; nefesd yalnızca okur.
  Kullanıcının "asla dondurma" listesi yerleşik korunan listeye **eklenir**, onu daraltamaz.
  Komut satırında açıkça verilen `--stall-ms` / `--max-frozen` dosyadan önceliklidir.
- **Sözleşme (yalnızca ekleme):** `GetStatus() → (b, s, d)`, `SetEnabled(b)`, `ReloadSettings() → (b, s)`,
  `RecentEvents() → a(tsss)`, sinyal `StatusChanged(b, s)`, `AppResumed.reason` için `"paused"`.
- **Yoklama yok:** simge sinyallerle güncellenir; `GetStatus` yalnızca pencere görünürken çağrılır.

## Değerlendirilen alternatifler
- **Gtk.StatusIcon:** bağımlılıksız, sol tık doğrudan pencere; ama GTK'da deprecated, HiDPI'da bulanık.
- **Ayrı `nefes-panel` süreci:** temiz ayrım; ama bellek baskısı aracı için fazladan ~25–30 MB.
- **Ayarların D-Bus üzerinden nefesd'de tutulması (`SetSettings`):** dosya elle düzenlenemez, nefesd
  yeniden başlayınca kalıcılık için yine dosya gerekir.

## Sonuçlar
- Eski tüketiciler (yalnızca `Resume`/`ListFrozen`/iki sinyal kullananlar) etkilenmez.
- nefes-agent artık GTK 3 yükler → ajanın RSS'i artar; M5 yalnızca nefesd için tanımlı, ajan ayrıca not edilir.
- GNOME'da simge için eklenti gerekir ([[ADR-0002 Asgari ürün Xfce]] gereği ek işlev).
