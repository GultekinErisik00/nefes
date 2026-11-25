---
tags: [nefes, olcum]
---
# Başarı Ölçütleri

## Test düzeni
- Pardus 25 **Xfce** VM: **4 GB RAM, 2 vCPU** (+ mümkünse 4 GB'lık eski dizüstü) — şu an `userpardus` 2 GB / 1 vCPU, yükseltilecek ([[Test Ortamı]])
- Yük: yerel kaydedilmiş sayfalarla 20 sekmeli Firefox + büyük Calc dosyası + belleği kademeli tüketen betik (stress-ng / kendi sızıntı benzetimi)
- Yapılandırmalar: **varsayılan Pardus · earlyoom · Nefes** — her biri **5 tekrar**, ortalama ± standart sapma

| Ölçüt | Nasıl ölçülür | Hedef | Son değer |
|---|---|---|---|
| M1 Arayüz yanıt gecikmesi | 100 ms aralıklı GTK zamanlayıcı gecikmesi (maks, p99) | p99 < 500 ms, maks < 2 s | ✅ Nefes p99 58 ± 5 ms, maks 91 ± 7 ms (5/5); varsayılan 2/5 ([[Deney 05 Ölçüm Turu]]) |
| M2 Toplam donma süresi | gecikme > 1 s aralıkların toplamı | varsayılana göre ≥ %80 azalma | ✅ 0,7 ± 0,7 s → 0 s (−%100); taban düşük, gerçek uygulamalarla tekrarlanmalı ([[Deney 05 Ölçüm Turu]]) |
| M3 Veri kaybı | sonlandırılan uygulama sayısı; Calc kaydedilebiliyor mu | Seviye 3 olmadan 0 | ✅ 0 (her üç yapılandırmada; earlyoom bu yükte tetiklenmedi) ([[Deney 05 Ölçüm Turu]]) |
| M4 Devam ettirme süresi | "Devam ettir" → etkileşime hazır | ölç, hedef < 5 s | ✅ 1,57 s (zram, 400 MB) ([[Deney 03 Uçtan Uca nefesd]]) |
| M5 Servis maliyeti | nefesd CPU/RSS (boşta, baskıda) | CPU < %1, RSS < 30 MB | ✅ boşta CPU %0,00 / RSS 10,1 MB; baskıda (1 dondurma) CPU %0,79 / RSS 12,7 MB — 25 Kas, `deneyler/m5_maliyet.sh` |
| M6 Doğruluk | birim test: korunan liste ve odak asla dondurulmaz | tüm testler geçer | ✅ 216 birim + 6 VM testi geçiyor (karar motoru M6 testleri dahil) |

## Ölçüm turları
- [ ] Hafta 2 — ilk ölçümler (varsayılan, earlyoom)
- [ ] Hafta 7 — 1. tur (ara sonuç tablosu)
- [ ] Hafta 10 — nihai tur (5 × 3)

Tur notları için şablon: [[Ölçüm Turu]]
