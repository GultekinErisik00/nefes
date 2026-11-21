---
tags: [nefes, deney, olcum]
tarih: 2026-11-21
makine: userpardus
betik: deneyler/freeze_spike.sh
---
# Deney 01 — Dondur → geri kazan → devam (spike)

**Amaç:** Projenin çekirdek fikri ([[cgroup v2#cgroup.freeze]] + [[memory.reclaim]]) gerçek Pardus'ta çalışıyor mu, root olmadan yapılabiliyor mu, maliyeti ne?

**Ortam:** [[Test Ortamı]] — Pardus 25.2 Xfce, kernel 6.12.95, 1 vCPU, 2 GB RAM, **disk swap** (`/dev/sda5`, 1.1 GB), zram yok. Kullanıcı `user`, **sudo yok**.

**Yöntem:** `systemd-run --user --scope` ile `app.slice` altında kendi scope'unda 400 MB özel anonim bellek tutan Python işçisi; her 0,5 sn tüm sayfalara dokunup süreyi logluyor. Sırayla: dondur → 2 sn bekle → `memory.reclaim 400M` → çöz → ilk tam geçişin bitmesini bekle.

Çalıştırma: `ssh userpardus 'bash -s 400' < deneyler/freeze_spike.sh`

## Sonuçlar (çalıştırma 2, MAP_PRIVATE)
| Adım | Ölçüm |
|---|---|
| Başlangıç | current 403 MB, anon 402 MB, swap 0 |
| Dondurma (`cgroup.freeze=1` → `cgroup.events frozen 1`) | **18 ms** |
| Donukken ilerleme | 2 sn'de **0** dokunma ✅ (görev durumu `S`) |
| `memory.reclaim 400M` | **3,06 s**; current 403 → **4 MB**, swap 0 → 402 MB; yazma **EAGAIN** döndü (istenen 400M'nin tamamı alınamadı ama ~399 MB alındı) |
| Çözme (`cgroup.freeze=0`) | **30 ms** |
| **Devam gecikmesi** (çözmeden ilk tam geçişe) | **10,0 s** — 400 MB diskten geri sayfalandı (~40 MB/s) ❌ M4 hedefi < 5 s |
| Sonraki geçişler | 57–76 ms (normal) |
| Çözme sonrası | current 401 MB; swap 402 MB (swap önbelleği kopyayı tutuyor — normal) |
| Artık scope | yok (temizlik çalıştı) |

Çalıştırma 1 (`mmap(-1)` = paylaşımlı → shmem olarak sayıldı): reclaim 6,4 s, sonuç benzer. Gerçekçi ölçüm için **özel anonim bellek** kullanılmalı.

## Çıkarımlar
1. ✅ **Fikir çalışıyor:** dondur + reclaim, uygulamanın RAM'ini ~%99 boşalttı; dondurma/çözme anlık (≤ 30 ms).
2. ✅ **Root gerekmiyor:** kullanıcının kendi `app.slice` scope'ları için `cgroup.freeze` ve `memory.reclaim` delegasyonla yazılabilir → prototipte nefesd kullanıcı servisi olarak başlayabilir ([[Kararlar]]: root mu kullanıcı mı).
3. ⚠️ **EAGAIN normal sonuç:** `memory.reclaim` istenenin tamamını alamazsa `EAGAIN` döner; kod bunu hata değil **kısmi başarı** saymalı ve `memory.current`'i yeniden okumalı.
4. ❌ **Disk swap ile devam çok yavaş (10 s / 400 MB):** M4 (< 5 s) disk swap'la tutmaz → **[[zram]] isteğe bağlı değil, zorunlu.** Ayrıca reclaim 3 s sürdü → nefesd reclaim'i ana döngüyü bloklamadan (ayrı iş parçacığı / parçalı) yapmalı.
5. Önerilen sonraki deney: aynı betik **zram açıkken** (lz4 ve zstd) → devam süresi ve reclaim süresi karşılaştırması.

İlgili: [[Başarı Ölçütleri]], [[Karar Motoru]]
