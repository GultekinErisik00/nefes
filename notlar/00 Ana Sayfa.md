---
aliases: [Home, Başla]
tags: [nefes, dizin]
---
# Nefes — Ana Sayfa

> Öldürmek yerine dondur, belleği geri kazan, kullanıcının işini koru.

Öneri belgesi: ![[Gultekin_Erisik_Ali_Osman_Citak_461_Proje_Onerisi.pdf]]

## Proje
- [[Proje Özeti]] — problem, senaryo, net katkı
- [[Başarı Ölçütleri]] — M1–M6 ve test düzeni
- [[Takvim]] — 12 haftalık plan ve ilerleme
- [[Riskler]]
- [[Test Ortamı]] — `ssh userpardus` durum notu

## Mimari
- [[Bileşenler]] — nefesd, nefes-agent, eklenti, nefes-zram, nefes-olcum
- [[D-Bus Sözleşmesi]] — servis ↔ ajan ↔ eklenti arayüzü (taslak)
- [[Karar Motoru]] — aday seçimi ve kademeli eylem
- ![[Mimari.canvas]]

## Çekirdek notları
- [[PSI]] · [[cgroup v2]] · [[memory.reclaim]] · [[zram]] · [[OOM Killer]]

## Deneyler
- [[Deney 01 Dondur Geri Kazan]] — freeze 18 ms, reclaim 403→4 MB, devam 10 s (disk swap)
- [[Deney 02 zram Karşılaştırma]] — devam: disk 9,1 s → zram lz4 0,88 s / zstd 0,79 s
- [[Deney 04 Ölçüm Önizlemesi]] — nefes-olcum ilk karşılaştırma: maks gecikme 217 → 66 ms; zram'lı makinede M2 ölçülemedi
- [[Deney 03 Uçtan Uca nefesd]] — nefesd baskıda 495 MB'lık uygulamayı dondurdu, baskı bitince çözdü; tetikleyici fazla hassas

## Çalışma
- [[Kararlar]] — mimari karar kayıtları (ADR)
- Haftalık günlük: `04 Günlük/`
- Şablonlar: `Şablonlar/`
