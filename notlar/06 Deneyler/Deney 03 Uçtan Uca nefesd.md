---
tags: [nefes, deney, e2e]
tarih: 2026-11-21
makine: userpardus
betik: deneyler/e2e_nefes.sh
---
# Deney 03 — nefesd uçtan uca (ilk çalıştırma)

**Amaç:** Tüm zincir gerçek sistemde çalışıyor mu? PSI tetikleyicisi → [[Karar Motoru]] → `cgroup.freeze` + `memory.reclaim` → baskı bitince çözme → SIGTERM'de temizlik.

**Ortam:** [[Test Ortamı]] — Pardus 25.2 Xfce, 1 vCPU, 2 GB RAM, disk swap 1,1 GB, **zram yok**. nefesd kullanıcı olarak (root yok), X11 odak `DISPLAY=:0`. Tetikleyici `some 150 ms / 2000 ms`, `safe_below=1.0`.

**Yöntem:** kendi scope'unda 500 MB tutan "arka plan uygulaması" + ssh oturumunda `stress-ng --vm-bytes 1100M` 25 s ("ön plandaki iş").

## Sonuç
| Zaman | Olay |
|---|---|
| 23:57:56 | nefesd başladı |
| 23:58:03 | **DONDURULDU** arka plan uygulaması, **495 MB geri kazanıldı** (tetik geldiğinde some avg10 = 0,36) |
| stress-ng boyunca (25 s) | uygulama donuk kaldı, scope belleği **7–8 MB**; PSI some avg10 en çok 23,3 |
| 23:58:40 | **DEVAM** (neden: `pressure_low`) — stress-ng bittikten ~10 s sonra |
| SIGTERM | "dondurulan her şey çözüldü"; donuk ya da artık scope kalmadı |

## Çıkarımlar
1. ✅ **Zincir uçtan uca çalışıyor:** olay tabanlı PSI → karar → dondur + geri kazan → güvenli seviyede çöz → kapanışta çöz. Root gerekmedi.
2. ⚠️ **Tetikleyici fazla hassas:** uygulama **stress-ng başlamadan** dondu — kendi 500 MB'lık ayırmasının yarattığı kısa baskıda (avg10 = 0,36). `some 150 ms / 2 s` 2 GB'lık makinede geçici ayırma dalgalarını da yakalıyor. → Eşik ayarı (Hafta 7) gerekli; seçenekler: daha yüksek stall (ör. 300–500 ms), `full` tetikleyici, ya da "baskı N ardışık pencere sürsün" koşulu. → [[Kararlar]] (PSI eşikleri).
3. ✅ Odak izleme çalıştı (X11 `_NET_ACTIVE_WINDOW`), ssh'den başlatılan stress-ng doğru şekilde aday olmadı (oturum scope'u).
4. Betik düzeltildi: uygulama belleğini doldurduktan **sonra** nefesd başlatılıyor (bu çalıştırmada sıra yanlıştı, bu yüzden dondurma stress-ng'den önce oldu).
5. Ölçülmeyenler: devam sonrası uygulamanın tepki süresi (M4), zram ile davranış. Sonraki çalıştırma: zram açık + düzeltilmiş betik.

## Çalıştırma 2 (2026-11-22 00:01, sıra düzeltilmiş betik + hata yolu düzeltmeleri)
| t (stress-ng'den sonra) | Durum |
|---|---|
| 0 s | uygulama 504 MB, donuk değil (✅ artık kendi ayırmasında dondurulmuyor) |
| 3 s | baskı başladı (some avg10 27,9), henüz donuk değil |
| ~4–6 s | **DONDURULDU**, geri kazanım başladı: 502 → 312 → 101 → **1 MB** (~6 s sürdü; disk swap) — 500 MB geri kazanıldı |
| 6–24 s | donuk kaldı; PSI some avg10 en çok **72,3** (stress-ng'nin kendisi 1,1 GB + masaüstü → disk swap thrash) |
| stress-ng bitti + 30 s | **hâlâ donuk** — some avg10 1,0'ın altına inmedi |
| SIGTERM | **DEVAM (neden: shutdown)**, "dondurulan her şey çözüldü"; artık scope / donuk scope yok |

**Yeni bulgular:**
1. ⚠️ **Güvenli eşik çok sıkı:** `safe_below=1.0`; avg10 10 sn'lik üstel ortalama olduğundan 40'tan 1'in altına inmesi ~35–40 s sürüyor. Uygulama baskı bittikten sonra en az 30 s daha donuk kaldı. → `safe_below` daha yüksek olmalı (ör. 5–10) ve/veya "kullanılabilir bellek ≥ uygulamanın swap'taki boyutu" koşulu. → [[Kararlar]].
2. ⚠️ **Geri kazanım ana döngüyü ~6 s bloklıyor** (disk swap, yoğun baskı). Bu sürede yeni PSI olayları kuyrukta kaldı (günlükte art arda tikler). → zram ile kısalır ([[Deney 02 zram Karşılaştırma]]: 0,4–1 s); yine de reclaim'i ayrı iş parçacığına almak gerekli.
3. Karşılaştırma için **Nefes kapalı** aynı senaryo (varsayılan Pardus) ölçülmedi → M1/M2 için Hafta 7 ölçüm turunda.

## Çalıştırma 3 (2026-11-23 21:24) — arka plan geri kazanımı + yeni varsayılanlar
Değişiklik: reclaim ayrı iş parçacığında (`ThreadPoolExecutor(1)`), tetik `some 300 ms / 2 s` (150'den), `safe_below=5.0` (1,0'dan).

| | Çalıştırma 2 | **Çalıştırma 3** |
|---|---|---|
| stress-ng'den önce dondurma | yok ✅ | yok ✅ |
| Dondurma kararı → sonraki tur | ~6 s (reclaim döngüyü blokluyordu) | **7 ms** — döngü serbest ✅ |
| Geri kazanım | 500 MB, ~6 s (ana döngüde) | 437 MB, 3,5 s (arka planda) |
| Donukken scope belleği | 1 MB | 20 MB |
| stress-ng bittikten sonra çözme | **30 s içinde çözülmedi** (yalnızca SIGTERM'de) | **~14 s** sonra `pressure_low` ✅ |
| Kapanış | temiz | temiz; artık scope / süreç yok ✅ |

## Çalıştırma 4 (2026-11-23 21:34) — **zram açık** (nefes-zram: 1973 MB, zstd, öncelik 100)
| | Çalıştırma 3 (disk swap) | **Çalıştırma 4 (zram)** |
|---|---|---|
| Geri kazanım | 437 MB, 3,5 s | **501 MB, 2,3 s** |
| Donukken scope belleği | 20 MB | **1 MB** |
| PSI some avg10 tepe | 50,7 | **29,8** |
| stress-ng bittikten sonra çözme | ~14 s | **~0 s** (avg10 stress bitmeden 5'in altına indi) |
| **Devam sonrası ilk tam geçiş (M4)** | ölçülmedi | **1,57 s** ✅ (hedef < 5 s; [[Deney 01 Dondur Geri Kazan]]'da disk swap ile ~9–10 s) |
| Kapanış | temiz | temiz; artık scope / süreç yok ✅ |

**Sonuç:** zram ile zincirin tamamı hedeflerin içinde: daha hızlı ve daha çok geri kazanım, daha düşük sistem baskısı, baskı biter bitmez çözme ve gerçek devam süresi 1,6 s (M4 ✅). Bu, [[Deney 02 zram Karşılaştırma]]'daki "zram zorunlu" sonucunu uçtan uca doğruluyor.

**Sonuç (çalıştırma 3):** Deney 03'ün iki bulgusu giderildi. Kalan: çözme hâlâ PSI ortalamasının sönmesini bekliyor (~14 s); "kullanılabilir bellek yeterli" gibi ikinci bir koşul daha hızlı çözebilir. Eşikler Hafta 7 ölçüm turunda (zram açık, Nefes kapalı karşılaştırmasıyla) kesinleşecek.
