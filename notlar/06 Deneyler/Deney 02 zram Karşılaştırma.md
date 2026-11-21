---
tags: [nefes, deney, olcum, zram]
tarih: 2026-11-21
makine: userpardus
betik: deneyler/zram_deney.sh
---
# Deney 02 — Disk swap vs zram (lz4, zstd)

**Amaç:** [[Deney 01 Dondur Geri Kazan]]'da disk swap ile devam 10 s sürdü (M4 hedefi < 5 s). [[zram]] bunu düzeltiyor mu, hangi algoritma?

**Ortam:** [[Test Ortamı]] — Pardus 25.2 Xfce, kernel 6.12.95, 1 vCPU, 2 GB RAM, `vm.swappiness=60`. zram geçici: 1 GB, öncelik 100 (disk swap -2'nin üstünde), test sonunda kaldırıldı. Çekirdek algoritmaları: lz4, lz4hc, zstd, deflate.

**Yöntem:** Aynı `freeze_spike.sh`, 400 MB özel anonim bellek; her sayfa ~%25 rastgele (gerçekçi sıkıştırılabilirlik). Dondur → `memory.reclaim 400M` → çöz → ilk tam geçiş.
Çalıştırma: `sudo bash ~/nefes-deney/zram_deney.sh` (root: zram kurmak için; ölçüm kullanıcı olarak).

## Sonuçlar
| | Disk swap | zram **lz4** | zram **zstd** |
|---|---|---|---|
| Dondurma | 17 ms | 26 ms | 18 ms |
| Donukken ilerleme | 0 | 0 | 0 |
| `memory.reclaim` süresi | 3 174 ms | **397 ms** | 1 015 ms |
| RAM'de kalan (current) | 404 → 4 MB | 404 → 2 MB | 404 → 2 MB |
| Çözme | 32 ms | 32 ms | 49 ms |
| **Devam gecikmesi (M4)** | **9 110 ms** ❌ | **877 ms** ✅ | **788 ms** ✅ |
| İlk geçişin kendi süresi | 8 958 ms | 816 ms | 674 ms |
| Çözme sonrası swap'ta kalan | 403 MB (swap önbelleği) | 3 MB | 3 MB |
| PSI some avg10 (test sonu) | 0,07 | 3,26 | 3,47 |

(Disk swap sütunu: aynı gün 2. ölçüm; [[Deney 01 Dondur Geri Kazan]]'daki ilk ölçüm 10 001 ms.)

## Çıkarımlar
1. ✅ **zram, M4'ü sağlıyor:** devam 9,1 s → **< 0,9 s** (~11× hızlı). Disk swap ile hedef tutmuyor → **zram ön koşul** (nefes-zram asgari ürünün parçası, isteğe bağlı değil).
2. **lz4 vs zstd:** lz4 geri kazanımı ~2,5× hızlı (397 vs 1015 ms) — baskı anında RAM'i daha çabuk boşaltır; zstd devamda biraz hızlı (788 vs 877 ms) ve genelde daha iyi sıkıştırır (daha çok veri sığar). 1 vCPU'da fark küçük.
   → Öneri: **zstd varsayılan** (düşük RAM'de sıkıştırma oranı kritik), ama sıkıştırma oranı ölçülmeden karar kesinleşmez → [[Kararlar]].
3. Reclaim 0,4–1 s sürüyor → nefesd'de reclaim yine ana döngüyü bloklamamalı (ayrı iş parçacığı).
4. zram'dan geri okunan sayfalar zram'dan siliniyor (swap 3 MB kaldı); disk swap'ta kopya kalıyor. Normal davranış.

## Eksik / sonraki ölçüm
- ⚠️ **Sıkıştırma oranı ölçülemedi:** `zramctl` istatistiği çözme *sonrası* okundu (sayfalar geri gelmiş, zram boş). Betikte istatistik reclaim'den hemen sonra okunmalı → düzeltilecek.
- Tek tekrar; nihai turda 5 tekrar + gerçek uygulama (Firefox, Calc) gerekli ([[Başarı Ölçütleri]]).
- RAM 4 GB / 2 vCPU ile tekrarlanmalı.
