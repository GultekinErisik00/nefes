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
| M1 Arayüz yanıt gecikmesi | 100 ms aralıklı GTK zamanlayıcı gecikmesi (maks, p99) | p99 < 500 ms, maks < 2 s | – |
| M2 Toplam donma süresi | gecikme > 1 s aralıkların toplamı | varsayılana göre ≥ %80 azalma | – |
| M3 Veri kaybı | sonlandırılan uygulama sayısı; Calc kaydedilebiliyor mu | Seviye 3 olmadan 0 | – |
| M4 Devam ettirme süresi | "Devam ettir" → etkileşime hazır | ölç, hedef < 5 s | – |
| M5 Servis maliyeti | nefesd CPU/RSS (boşta, baskıda) | CPU < %1, RSS < 30 MB | – |
| M6 Doğruluk | birim test: korunan liste ve odak asla dondurulmaz | tüm testler geçer | – |

## Ölçüm turları
- [ ] Hafta 2 — ilk ölçümler (varsayılan, earlyoom)
- [ ] Hafta 7 — 1. tur (ara sonuç tablosu)
- [ ] Hafta 10 — nihai tur (5 × 3)

Tur notları için şablon: [[Ölçüm Turu]]
