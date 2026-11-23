---
tags: [nefes, karar, dbus]
durum: kabul
tarih: 2026-11-23
sorumlu: ortak
---
# ADR-0003 — D-Bus sözleşmesi: oturum veriyolu, `tr.edu.bil461.Nefes1`, XML tek kaynak

## Bağlam
nefesd ile nefes-agent (Ali Osman) arasında bir sınır var: ajan bildirim gösterir, "Devam ettir"i iletir. İki taraf paralel geliştiriliyor; alan adları/tipler kayarsa entegrasyon bozulur. Prototipte nefesd **kullanıcı servisi** olarak çalışıyor (cgroup delegasyonu yeterli, [[Deney 01 Dondur Geri Kazan]]). Odak bilgisini nefesd X11'den kendisi okuyor ([[ADR-0002 Asgari ürün Xfce]]).

## Karar
- **Tek yetkili kaynak:** `nefesd/tr.edu.bil461.Nefes1.xml` (D-Bus introspection XML). nefesd ve nefes-agent bu dosyayı `Gio.DBusNodeInfo.new_for_xml` ile yükler; şekil başka yerde (not, kod, mock) elle kopyalanmaz. [[D-Bus Sözleşmesi]] notu artık yalnızca gerekçe ve bağlam tutar.
- **Veriyolu: oturum (session).** Bus adı `tr.edu.bil461.Nefes1`, nesne `/tr/edu/bil461/Nefes1`, arayüz `tr.edu.bil461.Nefes1.Manager`.
- **Asgari yüzey (tüketicinin işlerinden):** `Resume(s)→b`, `ListFrozen()→a(ssu)`, sinyaller `AppFrozen(s,s,t)` ve `AppResumed(s,s)`.
- **Taslaktan çıkarılanlar:** `ReportFocus` (odak nefesd'de, X11), `GetStatus` ve `AppKilled` (Seviye 3 ve nefes-ayarlar ek işlev; ihtiyaç doğunca sözleşmeye *eklenerek* gelir).
- Değişiklik protokolü: önce XML → iki taraf onayı → sonra kod. Yeni `reason` değerleri geriye uyumlu ekleme sayılır.

## Değerlendirilen alternatifler
- **Sistem veriyolu (öneri belgesindeki tasarım):** root nefesd gerektirir; policy dosyası, sudo kurulumu, UID doğrulaması. Prototipte gereksiz karmaşıklık. **nefesd root sistem servisine geçerse** bu ADR yenilenir: sistem veriyolu + `/usr/share/dbus-1/system.d/` policy + her çağrıda `GetConnectionUnixUser` doğrulaması.
- Bus adı `io.github.nefes.Nefes1`: kuruma bağımsız; ama ekip taslaktaki adı seçti.

## Sözleşme değişiklikleri
- **2026-11-23 — `AppFrozen(s, s, t reclaimed_bytes)` → `AppFrozen(s, s, t memory_bytes)`**, dondurma anında yayınlanır. Neden: gerçek veriyolunda `AppResumed` `AppFrozen`'dan önce gelebiliyordu (geri kazanım arka planda bitince yayınlanıyordu). Tip aynı (`t`), ad ve anlam değişti; tüketici henüz yazılmadığı için uyumluluk etkisi yok. XML'e "aynı cgroup için AppFrozen her zaman AppResumed'dan önce" garantisi eklendi. → [[D-Bus Sözleşmesi]]

## Sonuçlar
- Oturum veriyolunda yalnızca aynı kullanıcının süreçleri bağlanabilir → yetki doğrulaması gerekmez.
- `Resume` güvenli: yalnızca nefesd'nin kendi dondurduğu uygulamaları çözer (`Daemon.resume`).
- Sözleşme testi: sağlayıcının ürettiği her sinyal/dönüş değerinin tipi XML'deki imzayla otomatik karşılaştırılır.
