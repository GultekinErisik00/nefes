---
tags: [nefes, karar]
durum: kabul
tarih: 2026-11-21
---
# ADR-0002 — Asgari ürün Xfce/X11 üzerinde, GNOME ek işlev

## Bağlam
Öneri belgesi asgari ürünü Pardus 25 GNOME'a göre tanımlamıştı (Xfce ek işlevdi). Test makinesi `userpardus` Pardus 25.2 **Xfce/X11** ([[Test Ortamı]]). Xfce uygulamaları ayrı cgroup'ta başlatmıyor: hepsi pencere yöneticisi ve panelle aynı `session-2.scope` içinde. Kod sıfırdan başlıyor ve plan ~3 hafta geride.

## Karar
- Asgari ürün **Pardus 25 Xfce (X11)** hedefler. GNOME desteği ek işleve iner.
- **Odak:** X11 `_NET_ACTIVE_WINDOW` → `_NET_WM_PID` → `/proc/PID/cgroup`. `python-xlib` VM'de kurulu; kök penceredeki `PropertyNotify` olayıyla olay tabanlı izlenir (yoklama yok). GNOME Shell eklentisi gerekmez → odak izleme oturum ajanına (nefes-agent) taşınır.
- **Uygulama izolasyonu:** `nefes-baslat` sarmalayıcısı uygulamaları `systemd-run --user --scope --unit=app-nefes-<ad>-<rastgele> -- <komut>` ile başlatır; böylece her uygulama `user@1000.service/app.slice/` altında kendi scope'unda olur. Kullanıcı `.desktop` geçersiz kılmaları (`~/.local/share/applications/`) ile menü/panel başlatıcıları sarmalayıcıya yönlendirilir.
- **Aday kuralı değişmez:** yalnızca `app.slice` altındaki scope'lar; `session-*.scope` kesin korunur (orada xfwm4, panel, masaüstü var).

## Değerlendirilen alternatifler
- GNOME kurmak / ayrı GNOME VM: öneriye birebir uyar, ama 2 GB'ta ağır, eklenti yazımı ek iş, zaman zaten geride.
- Çalışan süreçleri sonradan scope'a taşımak: `session-2.scope` root'a ait ve `user@1000.service` ile ortak yetkili ataları yok → kullanıcı taşıyamaz; root ile mümkün ama süreç ağacı (çocuklar) ve systemd'nin scope muhasebesiyle çatışma riski. Reddedildi (ileride root servis için tekrar bakılabilir).

## Sonuçlar
- Görev dağılımı: Ali Osman'ın "GNOME Shell eklentisi" görevi → **X11 odak izleme + nefes-baslat sarmalayıcısı**.
- Sarmalayıcı dışında başlatılan uygulamalar (terminalden açılanlar, zaten açık Firefox örneğine devredilen yeni pencereler) aday olmaz → "kapsanmayan bellek" olarak ölçüm raporunda belirtilmeli.
- Firefox gibi tek örnekli uygulamalarda ilk başlatma sarmalayıcıdan geçmeli; sonraki pencereler aynı scope'ta kalır.
- [[D-Bus Sözleşmesi]]'nde `ReportFocus` çağıranı artık nefes-agent.
- Rapor/sunumda öneriden sapma gerekçesiyle belirtilmeli.
