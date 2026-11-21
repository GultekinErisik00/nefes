---
tags: [nefes, cekirdek, nefes-zram]
kaynak: https://github.com/systemd/zram-generator
---
# zram

RAM içinde sıkıştırılmış blok aygıtı; swap olarak kullanılınca disk yerine RAM'e (sıkıştırarak, ~2–4×) yazılır. Eski, yavaş diskli makinelerde thrashing'i ciddi azaltır.

## zram-generator (Debian paketi: `systemd-zram-generator`)
`/etc/systemd/zram-generator.conf`:
```ini
[zram0]
zram-size = min(ram / 2, 4096)
compression-algorithm = zstd
swap-priority = 100
```
Uygulama: `systemctl daemon-reload && systemctl start systemd-zram-setup@zram0.service` · kontrol: `zramctl`, `swapon --show`.

## nefes-zram politikası (taslak — ölçümle belirlenecek)
| RAM | zram boyutu | algoritma |
|---|---|---|
| ≤ 2 GB | ram × 1.0 | zstd |
| 4 GB | ram × 0.75 | zstd |
| 8 GB | ram × 0.5 | lz4 |
| > 8 GB | min(ram/2, 8 GB) | lz4 |

- `vm.swappiness`: zram ile yüksek değer (100–180) yaygın; Pardus varsayılanını önce ölç.
- Mevcut disk swap'ı kaldırılmaz; zram daha yüksek öncelikle eklenir.
- Saf fonksiyon: `zram_config(ram_mb) -> str` → pytest ile test edilir.

## Ölçülen (2026-11-21) → [[Deney 02 zram Karşılaştırma]]
- 400 MB devam: disk swap **9,1 s**, zram lz4 **0,88 s**, zram zstd **0,79 s** → zram **zorunlu** (M4).
- Reclaim: disk 3,2 s, lz4 0,4 s, zstd 1,0 s.
- Pardus 6.12 çekirdeği: lz4, lz4hc, zstd, deflate destekli.
- Not: bu `zramctl` sürümünde `--reset` cihazı da siliyor; cihazı `zramctl --find` ile oluştur.

## VM'de doğrulanacak (Hafta 1 durum notu)
- [x] Pardus 25 varsayılanında swap var mı, zram var mı, earlyoom/systemd-oomd kurulu mu? → disk swap 1,1 GB, zram yok, OOM aracı yok ([[Test Ortamı]])
- [ ] lz4 / zstd sıkıştırma oranı (reclaim'den hemen sonra `zramctl` ile)

İlgili: [[memory.reclaim]], [[Bileşenler]]
