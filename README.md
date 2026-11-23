# Nefes

**Pardus için donma önleyici bellek baskısı yöneticisi** — BİL461 İşletim Sistemleri dönem projesi.

Bellek dolduğunda Linux thrashing'e girer ve OOM killer genellikle çok geç, yanlış uygulamayı öldürür. Nefes, PSI tetikleyicisiyle baskıyı erkenden yakalar, **odakta olmayan** en büyük uygulamanın cgroup'unu dondurur (`cgroup.freeze`), sayfalarını `memory.reclaim` ile zram'a iter ve kullanıcıya Türkçe bir "Devam ettir" bildirimi gösterir. Hiçbir uygulama sonlandırılmaz.

- Hedef: Pardus 25 Xfce / X11 (Debian 13, Linux 6.12, systemd 257); GNOME desteği ek işlev
- Dil: Python 3 (servis, ajan, ölçüm, `nefes-baslat` sarmalayıcısı)
- Lisans (planlanan): GPL-3.0-or-later
- Ekip: Gültekin Erişik, Ali Osman Çıtak

> Durum: v0.5.0 — asgari ürün çalışıyor, ölçüm turu (Hafta 7) sürüyor.

## Kurulum (Pardus 25 / Debian 13)
```bash
sudo apt install debhelper dpkg-dev          # yalnızca paketi derlemek için
dpkg-buildpackage -us -uc -b                 # depo kökünde → ../nefes_0.5.0_all.deb
sudo apt install ../nefes_0.5.0_all.deb      # zram yapılandırması da yazılır
```
Oturum yeniden açıldığında (ya da hemen `nefes-oturum` ile) `nefesd` ve `nefes-agent` systemd kullanıcı servisi olarak başlar; menüden açılan Firefox, LibreOffice ve GIMP kendi cgroup'unda çalışır.

- Durum: `systemctl --user status nefesd nefes-agent` · günlük: `journalctl --user -u nefesd`
- Donuk uygulamalar: `gdbus call --session --dest tr.edu.bil461.Nefes1 --object-path /tr/edu/bil461/Nefes1 --method tr.edu.bil461.Nefes1.Manager.ListFrozen`
- Kaldırma: `sudo apt purge nefes` (yalnızca nefes-zram'ın yazdığı zram yapılandırması da silinir); menü sarmalayıcılarını geri almak için önce `nefes-baslat --desktop-remove`.
- Güvenlik: servis çökse bile `ExecStopPost=nefesd --thaw-all` dondurulan her uygulamayı çözer.

Tasarım notları Obsidian vault'u olarak bu klasörde tutulur — Obsidian'da bu klasörü "Open folder as vault" ile açın, `notlar/00 Ana Sayfa.md` ile başlayın.
