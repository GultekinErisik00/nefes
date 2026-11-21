---
tags: [nefes, karar]
durum: kabul
tarih: 2026-10-20
---
# ADR-0001 — Python 3 + PyGObject, eklenti için JavaScript

## Bağlam
Pardus'un kendi araçları Python 3 + GTK yığınındadır; proje Pardus deposuna uygun .deb olarak dağıtılacak. GNOME Shell eklentileri yalnızca JavaScript (GJS, ESM) ile yazılabilir.

## Karar
- nefesd, nefes-agent, nefes-zram, nefes-olcum: **Python 3** (Debian 13 → 3.13), D-Bus ve bildirim için `python3-gi` (Gio, GLib, Notify).
- GNOME Shell eklentisi: **JavaScript (GNOME 48 ESM)**.
- PyPI'dan ek bağımlılık yok; yalnızca Debian paketleri.

## Değerlendirilen alternatifler
- C / Rust servis: daha düşük RSS (M5) ama Pardus yığınıyla uyumsuz, geliştirme süresi uzun.
- dbus-python / pydbus: Gio zaten python3-gi içinde; ek bağımlılık gereksiz.

## Sonuçlar
- M5 (RSS < 30 MB) Python + gi ile izlenmeli; aşarsa `gi` importlarını ajan tarafına sınırla.
- Öneri belgesi bölüm 5 ile tutarlı.
