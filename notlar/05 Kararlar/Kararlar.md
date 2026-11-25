---
tags: [nefes, karar, dizin]
---
# Kararlar (ADR dizini)

Yeni karar: `Şablonlar/Karar (ADR)` şablonuyla `05 Kararlar/ADR-NNNN Başlık.md` oluştur, buraya ekle.

| No | Karar | Durum | Tarih |
|---|---|---|---|
| [[ADR-0001 Python ve PyGObject]] | Servis/ajan Python 3 + PyGObject, eklenti JS | kabul | 2026-10-20 (öneri) |
| [[ADR-0002 Asgari ürün Xfce]] | Asgari ürün Xfce/X11; odak `_NET_ACTIVE_WINDOW`, uygulamalar `nefes-baslat` ile scope'a | kabul | 2026-11-21 |
| [[ADR-0003 D-Bus sözleşmesi]] | Oturum veriyolu, `tr.edu.bil461.Nefes1`, introspection XML tek kaynak | kabul | 2026-11-23 |
| [[ADR-0004 Arayüz ve sözleşme genişletmesi]] | Panel simgesi + pencere nefes-agent içinde; ayar dosyası (tek yazar ajan); sözleşmeye yalnızca ekleme | kabul | 2026-11-25 |

## Bekleyen kararlar
- [ ] nefesd root sistem servisi mi, kullanıcı servisi mi (cgroup delegation yeterli olabilir)?
- [ ] zram algoritması: zstd mi lz4 mü? (devam ~eşit; lz4 reclaim 2,5× hızlı; oran henüz ölçülmedi) → [[Deney 02 zram Karşılaştırma]]
- [ ] D-Bus bus adı ve arayüz → [[D-Bus Sözleşmesi]]
- [ ] Seviye 3 (sonlandırma) varsayılan açık mı? → [[Karar Motoru]]
- [ ] Reclaim miktarı ve adımlama → [[memory.reclaim]]
- [ ] Azami dondurma süresi (güvenlik zamanlayıcısı) varsayılanı
- [ ] PSI eşik değerleri (Hafta 7 ölçüm turundan sonra kesinleşecek) — geçici varsayılanlar: tetik `some 300ms/2s`, `safe_below=5.0` ([[Deney 03 Uçtan Uca nefesd]] çalıştırma 3: çözme 30 s+ → ~14 s)
- [x] **Asgari donukluk süresi** (2026-11-23): `Policy.min_frozen_seconds = 30` — `pressure_low` çözmesi ancak 30 s donukluktan sonra (odak/zaman aşımı/kullanıcı etkilenmez). Neden: tetik kısa süreli beklemeyle gelir ama avg10 o an zaten < 5 olabiliyordu → uygulama 2 s içinde donup çözülüyordu (zram açıkken Pardus'ta görüldü). `--min-frozen` ile ayarlanır.
- [x] Reclaim ana döngüden ayrı iş parçacığına alındı (2026-11-23) — tek işçili kuyruk; arka plan işi daemon durumuna dokunmaz
