---
tags: [nefes, cekirdek]
kaynak: https://lwn.net/Articles/890743
---
# memory.reclaim

Cgroup'tan **hedefli, proaktif** geri kazanım (Linux **5.19+**). Projenin "dondur + geri kazan" fikrinin ikinci yarısı.

```
echo "512M" > <cgroup>/memory.reclaim
```
- Değer bayt cinsinden (K/M/G sonekleri kabul edilir).
- İstenen miktar geri kazanılamazsa yazma `EAGAIN` döner → Python'da `BlockingIOError`/`OSError(errno.EAGAIN)` yakala, kısmi başarı say.
- Anonim sayfalar ancak **swap varsa** geri kazanılabilir → [[zram]] ön koşul. Swap yoksa yalnızca sayfa önbelleği (file) boşalır.
- Donmuş cgroup'ta da çalışır (sayfalar donmuş süreçlerden alınır; devam edince sayfa hatasıyla geri gelir → M4 süresi).
- Ne kadar istenmeli? Seçenek: `memory.current`'in büyük kısmı, parçalar hâlinde (örn. 256M adımlarla, baskı düşene kadar) — [[Kararlar]]'a karar olarak yazılacak.

## VM'de doğrulanacak
- [x] Reclaim sonrası `memory.swap.current` artıyor, `memory.current` düşüyor mu? → Evet: 403 → 4 MB, swap +402 MB; tamamı alınamayınca **EAGAIN** ([[Deney 01 Dondur Geri Kazan]])
- [x] Kullanıcı (root olmadan) kendi `app.slice` scope'una yazabiliyor mu? → Evet (systemd delegasyonu)
- [ ] Pardus 6.12 çekirdeğinde `swappiness=` argümanı destekleniyor mu (sürüm geçmişini kontrol et)?
- [ ] 1 GB'lık Firefox için reclaim süresi (zram + zstd)?

İlgili: [[cgroup v2]], [[zram]]
