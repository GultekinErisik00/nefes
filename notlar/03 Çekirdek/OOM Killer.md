---
tags: [nefes, cekirdek]
---
# OOM Killer ve kullanıcı alanı araçları

## Çekirdek OOM killer
- Ancak bir bellek ayırma, geri kazanım denemelerinden sonra **tamamen başarısız** olunca çalışır → o ana kadar sistem uzun süre thrashing'de kalır.
- Kurban seçimi `oom_score` (bellek kullanımı + `oom_score_adj`) ile; odakta mı, kaydedilmemiş iş var mı bilmez.
- Nefes'te **son güvence olarak kalır**; devre dışı bırakılmaz.

## Karşılaştırma
| Araç | Tetik | Eylem | Eksiği (Nefes'e göre) |
|---|---|---|---|
| earlyoom | boş RAM + swap yüzdesi | en yüksek oom_score'u öldür | veri kaybı, odak bilmez, PSI kullanmaz |
| nohang | PSI / bellek, yapılandırılabilir | öldür + bildirim | dondur/geri al yok, karmaşık yapılandırma, Türkçe yok |
| systemd-oomd | PSI + cgroup v2 | bütün cgroup'u öldür | açıklama / geri alma yok |
| **Nefes** | PSI tetikleyicisi | **dondur + reclaim**, Türkçe bildirim, devam | — |

Karşılaştırma ölçümleri: [[Başarı Ölçütleri]]
