---
tags: [nefes, deney, olcum]
tarih: 2026-11-23
makine: userpardus
betik: deneyler/olcum_turu.sh, deneyler/olcum_senaryo.sh
---
# Deney 05 — Hafta 7 ölçüm turu (varsayılan / earlyoom / Nefes × 5)

**Ortam:** [[Test Ortamı]] — Pardus 25.2 Xfce, 1 vCPU, 2 GB RAM, disk swap 1,1 GB; nefes 0.5.0 paketi (tur başında güncel koddan yeniden kurulur).
**Senaryo** (`olcum_senaryo.sh`): 3 arka plan uygulaması (300+300+200 MB, `nefes-baslat` ile, 2 s'de bir sayfalarına dokunur) + 5. s'de ön plan işi `stress-ng` 1300 MB, 40 s; prob 60 s (100 ms). M3 = ölen arka plan uygulaması + öldürülen ön plan işi.
**Yapılandırmalar:** varsayılan (yalnız disk swap) · earlyoom (disk swap + earlyoom) · nefes (zram + nefesd + nefes-agent). Tekrarlar iç içe; her çalıştırmadan önce swap boşaltılır, sayfa önbelleği atılır.

## Çalıştırma 1 (2026-11-23 23:30) — ❌ GEÇERSİZ (yapılandırma hatası)
Günlükteki swap durumu: **earlyoom çalıştırmalarında zram AÇIKTI, nefes çalıştırmalarında zram KAPALIYDI.**
Neden: zram swap'ını systemd'nin `dev-zram0.swap` birimi yönetir. Betik `systemctl restart systemd-zram-setup@zram0` (aç) ve `swapoff /dev/zram0` (kapat) kullandı; swap birimi **gecikmeli** devreye girdi → zram bir sonraki yapılandırmaya kaydı. Etiketler yanlış olduğundan bu sayılar yapılandırmalar arası karşılaştırma için kullanılamaz.

Ham özet (yalnızca kayıt için; etiketler yanlış):

| etiket (gerçek durum) | p99 ms | maks ms | M2 s | M3 | PSI some maks |
|---|---|---|---|---|---|
| varsayilan (disk swap) ✅ | 60 ± 57 | 647 ± 604 | 0,3 ± 0,7 | 0 | 67,2 ± 8,9 |
| "earlyoom" (gerçekte zram + earlyoom) | 59 ± 3 | 100 ± 29 | 0,0 | 0 | 95,8 ± 0,4 |
| "nefes" (gerçekte disk swap + nefesd, zram yok/geç) | 25 ± 5 | 101 ± 59 | 0,0 | 0 | 58,2 ± 6,7 |

Yine de çıkan gözlemler (kesin değil):
- **earlyoom hiç tetiklenmedi** (M3 = 0): eşikleri (boş RAM ve swap < %10) bu yükte aşılmadı.
- **Yük zayıf:** varsayılan Pardus'ta bile yalnızca 1/5 çalıştırmada 1 s'yi aşan donma oldu (M2 ort. 0,3 s) → M2'nin "%80 azalma" hedefi bu yükle sınanamaz.

**Düzeltme (betik):** zram artık `systemctl start/stop dev-zram0.swap` ile (eşzamanlı) değiştiriliyor; her çalıştırmadan önce `verify` zram/earlyoom/nefesd durumunu kontrol ediyor, uyuşmazsa tur durur. Bir sonraki turda ön plan yükü artırılmalı (ör. 1500–1600 MB) ki varsayılan Pardus'ta gerçek donma (M2) ve muhtemelen OOM kaybı (M3) görülsün.

## Çalıştırma 2 (2026-11-25 00:43) — ✅ GEÇERLİ · ön plan yükü 1500 MB
Yapılandırma sorunu iki deneme daha aldı; ikisini de `verify` turu başlamadan durdurarak yakaladı:
- `systemctl stop dev-zram0.swap` → `systemctl start earlyoom` (sysinit → swap.target) zram'ı geri açtı.
- `systemctl mask --runtime --now` → zram yine açık kaldı ("dependency job for dev-zram0.swap failed").
- **Çözüm:** systemd birimi devreden çıkarıldı; zram doğrudan `swapon -p 100` / `swapoff`, kapatma tüm `systemctl start`'lardan sonra. 15/15 çalıştırmada durum satırı doğru (varsayılan: yalnız disk swap · earlyoom: disk swap + earlyoom açık · nefes: disk swap + zram + nefesd).

| yapılandırma (n=5, ort. ± sapma) | p99 | **maks** | **M2 donma** | M1 ✓ | M3 | PSI some tepe |
|---|---|---|---|---|---|---|
| varsayılan (disk swap) | 523 ± 154 ms | **1061 ± 212 ms** | 0,7 ± 0,7 s | 2/5 | 0 | 77,1 ± 7,0 |
| earlyoom | 54 ± 39 ms | 597 ± 394 ms | 0,2 ± 0,5 s | 5/5 | 0 | 75,5 ± 5,2 |
| **nefes** (zram + nefesd) | **58 ± 5 ms** | **91 ± 7 ms** | **0,0 s** | **5/5** | **0** | 96,2 ± 0,6 |

Ham veri: VM `~/nefes/olcumler/tur-20261125-0043/` (+ `ozet.txt`).

### Yorum
- **M1 ✓:** Nefes 5/5 çalıştırmada p99 < 500 ms ve maks < 2 s; varsayılan Pardus yalnızca 2/5. Nefes'te en kötü gecikme **1061 → 91 ms (−%91)** ve tekrarlar arası sapma çok düşük (±7 ms) — davranış öngörülebilir.
- **M2 ✓ (temkinli):** toplam donma 0,7 s → 0 s (−%100, hedef ≥ %80). Ancak taban düşük: bu yükte varsayılan Pardus bile çalıştırma başına en çok 1,2 s dondu; öneri belgesindeki "dakikalarca donma" senaryosu için daha ağır yük ve gerçek uygulamalar (Firefox/Calc) gerekir.
- **M3:** hiçbir yapılandırmada uygulama ölmedi; **earlyoom bu yükte hiç tetiklenmedi** (eşikleri: boş RAM ve swap < %10). earlyoom satırındaki iyileşme bu yüzden earlyoom'un bir eylemine bağlanamaz — çalıştırma sırası/sistem durumu etkisi olabilir; açıklanmamış olarak not edildi.
- **PSI some yüksek (96) ama arayüz akıcı:** zram'a sıkıştırma/açma zamanı bellek beklemesi olarak sayılıyor; PSI "sistem meşgul" der, "arayüz donuk" demez — ölçüt olarak gecikme probunun neden gerekli olduğunu gösteriyor.
- Kurulum günlüğünde `systemd-zram-setup@zram0.service failed` iletisi: postinst zram zaten kullanımdayken başlatmaya çalışıyor (`|| true`, zararsız) → postinst'te "zaten açıksa başlatma" düzeltmesi yapılacak.
