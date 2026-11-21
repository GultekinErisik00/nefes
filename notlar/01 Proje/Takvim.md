---
tags: [nefes, plan]
---
# Takvim ve İlerleme

G: Gültekin · A: Ali Osman. Dönem sonu varsayımı: Ocak 2027'nin ilk haftaları.

| Hf | Tarih | İş | Sorumlu | Çıktı | Durum |
|---|---|---|---|---|---|
| 1 | 21–27 Eki | Pardus 25 VM'leri; varsayılan bellek ayarlarının incelenmesi; öneri teslimi | G, A | test ortamı, durum notu, öneri | ✅ öneri · ✅ durum notu 21 Kas ([[Test Ortamı]]) |
| 2 | 28 Eki–3 Kas | Donmanın tekrarlanabilir oluşturulması; gecikme probu, PSI kaydedici | G: yük, A: ölçüm | varsayılan + earlyoom ilk ölçüm | ❌ yapılmadı |
| 3 | 4–10 Kas | PSI tetikleyicisi + cgroup keşfi (CLI); GNOME odak eklentisi | G: servis, A: eklenti | izleme + odak | ❌ yapılmadı |
| 4 | 11–17 Kas | Dondur, memory.reclaim, devam; korunan liste; ajan taslağı | G: eylem, A: ajan | elle dondur/devam | ❌ yapılmadı |
| 5 | 18–24 Kas | **D-Bus sözleşmesi**, servis–ajan entegrasyonu, uçtan uca | G, A | **v0.1** | ⏳ şu an — kod sıfırdan başlıyor (21 Kas) |
| 6 | 25 Kas–1 Ara | nefes-zram; karar motoru birim testleri; güvenlik zamanlayıcısı | G: zram, A: test | nefes-zram, pytest | |
| 7 | 2–8 Ara | 1. ölçüm turu, eşik ayarı, hata düzeltme | G, A | ara sonuç tablosu | |
| 8 | 9–15 Ara | Debian paketleme + systemd; nefes-ayarlar (ek) | G: paket, A: arayüz | .deb v0.5 | |
| 9 | 16–22 Ara | Xfce (ek), memory.high kısma; gerçek donanım | A: Xfce, G: kısma | ek işlevler | |
| 10 | 23–29 Ara | Nihai ölçüm (5×3), grafikler, kurulum belgesi | G, A | sonuç raporu, README | |
| 11 | 30 Ara–5 Oca | Demo provası, video, rapor | A: video, G: demo | video, rapor taslağı | |
| 12 | 6–10 Oca | Tampon, son düzeltmeler, teslim | G, A | v1.0 | |

> **21 Kasım: kod sıfırdan başlıyor — plan ~3 hafta geride.** Telafi: 2–5. haftaların çekirdek işleri (PSI izleme, cgroup keşfi, dondur/geri kazan/devam, karar motoru testleri) 5–6. haftalara sıkıştırılır; 12. hafta tamponu kullanılabilir. Kapsam daraltma sırası: nefes-ayarlar → memory.high → ikinci masaüstü desteği (GNOME veya Xfce, hangisi asgari üründe değilse).

Haftalık ayrıntı: `04 Günlük/`
