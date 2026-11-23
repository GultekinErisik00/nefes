---
tags: [nefes, deney, olcum]
tarih: 2026-11-23
makine: userpardus
betik: deneyler/olcum_karsilastirma.sh
---
# Deney 04 — nefes-olcum ile ilk karşılaştırma (önizleme, 1 tekrar)

**Amaç:** nefes-olcum'un (gecikme probu + PSI kaydedici) çalıştığını göstermek ve [[Başarı Ölçütleri]] M1/M2'nin ilk değerlerini almak.

**Ortam:** [[Test Ortamı]] — Pardus 25.2 Xfce, 1 vCPU, 2 GB RAM, **zram açık** (1973 MB zstd) + disk swap.
**Senaryo:** 500 MB arka plan uygulaması (`nefes-baslat` ile, her saniye sayfalarına dokunur) + 5. saniyede `stress-ng --vm-bytes 1500M` 30 s; prob 45 s kayıt (100 ms aralık). Nefes açık çalıştırmada `nefesd --no-dbus`.

## Sonuç
| | örnek | p99 | maks | M2 donma | M1 | PSI some avg10 tepe |
|---|---|---|---|---|---|---|
| Nefes **kapalı** | 410 | 52 ms | **217 ms** | 0,0 s | ✓ | **91,2** |
| Nefes **açık** | 416 | 49 ms | **66 ms** | 0,0 s | ✓ | **66,7** |

nefesd: 23:10:28 arka plan uygulamasını dondurdu (327 MB), baskı süresince donuk tuttu, kapanışta çözdü.

## Yorum
- **Nefes açıkken en kötü gecikme 217 → 66 ms (−%70)**, sistem baskı tepesi 91 → 67.
- **M2 karşılaştırılamaz:** Nefes kapalıyken de prob hiç 1 s'yi aşan donma yaşamadı. Nedeni: test makinesinde artık **zram kurulu** — varsayılan Pardus'ta zram yok (disk swap). zram tek başına bu senaryodaki donmayı büyük ölçüde engelliyor ([[Deney 02 zram Karşılaştırma]]). Ayrıca prob küçük ve sürekli aktif; gerçek bir masaüstü uygulamasından daha az sayfa kaybeder.
- Tek tekrar: istatistiksel sonuç değildir.

## Hafta 7 ölçüm turu için çıkarımlar
1. **"Varsayılan Pardus" yapılandırması zram'sız olmalı** (öneride tanımlandığı gibi: disk swap, OOM aracı yok). Ölçümden önce zram kapatılmalı: `sudo swapoff /dev/zram0` (ya da zram-generator yapılandırmasını kaldırıp yeniden başlat), Nefes çalıştırmasında yeniden açılmalı. Aksi hâlde Nefes'in katkısı zram'ın katkısından ayrılamaz.
2. Üç yapılandırma: **varsayılan** (disk swap) · **earlyoom** (disk swap + earlyoom) · **Nefes** (zram + nefesd). İsteğe bağlı dördüncü: "yalnız zram" — zram'ın ve nefesd'nin katkısını ayırmak için.
3. Yük gerçekçi olmalı: Firefox (20 sekme) + Calc büyük dosya `nefes-baslat` ile; prob yerine/yanında Calc'ın yanıt süresi.
4. 5 tekrar, ortalama ± standart sapma (`nefes_olcum ozet` tablo verir; ortalama/sapma eklenecek).
