---
tags: [nefes, proje]
kaynak: "[[Gultekin_Erisik_Ali_Osman_Citak_461_Proje_Onerisi.pdf]]"
---
# Proje Özeti

## Problem
4 GB veya daha az RAM'li Pardus makinelerinde (kamu, okullar) bellek dolunca çekirdek önce sayfa önbelleğini boşaltır ve swap'a yazar → **thrashing**: fare takılır, sistem dakikalarca yanıt vermez. [[OOM Killer]] ancak ayırma tamamen başarısız olunca devreye girer ve kaydedilmemiş işi tutan uygulamayı da öldürebilir. earlyoom / nohang / systemd-oomd ise sorunu **sonlandırarak** çözer → veri kaybı.

## Kullanım senaryosu
Memur: Firefox (15 sekme) + Calc (büyük tablo) + video konferans. Pivot tablo → bellek dolar → donma → güç düğmesi → tablo kaybolur.
**Nefes ile:** baskı eşiği aşılınca odakta olmayan en büyük uygulama (Firefox) dondurulur, sayfaları zram'a itilir, Calc akıcı kalır, Türkçe bildirim: *"Firefox, sistemin donmaması için geçici olarak duraklatıldı. [Devam ettir]"*.

## Net katkı (özgün kısım = politika + kullanıcı deneyimi)
1. **Dondur + geri kazan + devam ettir** — dondurmak tek başına RAM boşaltmaz; [[cgroup v2#cgroup.freeze]] + [[memory.reclaim]] birlikte çekirdek fikirdir.
2. **Odak farkındalığı** — odaktaki uygulama asla dondurulmaz (Xfce/X11'de `_NET_ACTIVE_WINDOW` → nefes-agent → D-Bus; öneride GNOME Shell eklentisiydi → [[ADR-0002 Asgari ürün Xfce]]).
3. **Kademeli eylem** — Seviye 1 `memory.high` (ek), Seviye 2 dondur+geri kazan, Seviye 3 bildirerek en büyük donmuşu sonlandır (yapılandırılabilir).
4. **Güvenli aday seçimi** — yalnızca `app.slice` scope'ları; kesin korunan liste.
5. Türkçe bildirim, tek tık devam ettirme, sıfır yapılandırma.
6. Otomatik [[zram]] yapılandırması.
7. Ölçüm araçları (gecikme probu, PSI kaydedici) → varsayılan Pardus / earlyoom / Nefes karşılaştırması.

## Dersle bağlantı
Sanal bellek & geri kazanım · swap/zram · cgroups v2 · süreç durumları (dondurulmuş görevler) · çekirdek–kullanıcı alanı iletişimi ([[PSI]] + `poll()`) · OOM · systemd + D-Bus IPC.

İlgili: [[Bileşenler]], [[Başarı Ölçütleri]], [[Takvim]]
