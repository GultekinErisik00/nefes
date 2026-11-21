---
tags: [nefes, cekirdek]
kaynak: https://docs.kernel.org/accounting/psi.html
---
# PSI — Pressure Stall Information

Görevlerin bir kaynağı (bellek) **beklerken** geçirdiği zamanın oranı. Boş bellek yüzdesinden daha iyi bir donma göstergesi.

## Okuma
```
$ cat /proc/pressure/memory
some avg10=0.00 avg60=0.00 avg300=0.00 total=0
full avg10=0.00 avg60=0.00 avg300=0.00 total=0
```
- `some`: en az bir görev bellek bekliyor · `full`: tüm etkin görevler bekliyor (gerçek donma)
- `total` µs cinsinden kümülatif. Cgroup başına: `<cgroup>/memory.pressure` (aynı biçim).

## Tetikleyici (olay tabanlı — M5 için kritik)
```python
fd = os.open("/proc/pressure/memory", os.O_RDWR | os.O_NONBLOCK)
os.write(fd, b"some 150000 1000000\0")   # 1 sn pencerede 150 ms stall
p = select.poll(); p.register(fd, select.POLLPRI)
while True:
    for _, ev in p.poll():            # baskı yokken bloklar → CPU ≈ 0
        if ev & select.POLLERR: ...   # izlenen kaynak gitti
        if ev & select.POLLPRI: on_pressure()
```
- Biçim: `<some|full> <stall_us> <window_us>`; pencere 500 ms – 10 s.
- fd **açık kalmalı**; kapatınca tetikleyici silinir.
- Ayrıcalıksız kullanıcılar için kısıtlar var (pencere 2 sn'nin katı) — nefesd root, sorun değil; ama ölçüm aracı (`nefes-olcum`) root değilse dikkat.
- Bir pencerede en fazla bir olay üretir (hız sınırlı).

## Açık sorular / VM'de doğrulanacak
- [ ] Pardus 25 çekirdeğinde PSI etkin mi? (`cat /proc/pressure/memory` çalışıyor mu)
- [ ] Hangi eşik değerleri thrashing başlangıcını yakalıyor? (Hafta 7 ayar turu)

İlgili: [[Bileşenler]], [[cgroup v2]]
