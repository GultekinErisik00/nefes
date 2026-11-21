# Nefes

**Pardus için donma önleyici bellek baskısı yöneticisi** — BİL461 İşletim Sistemleri dönem projesi.

Bellek dolduğunda Linux thrashing'e girer ve OOM killer genellikle çok geç, yanlış uygulamayı öldürür. Nefes, PSI tetikleyicisiyle baskıyı erkenden yakalar, **odakta olmayan** en büyük uygulamanın cgroup'unu dondurur (`cgroup.freeze`), sayfalarını `memory.reclaim` ile zram'a iter ve kullanıcıya Türkçe bir "Devam ettir" bildirimi gösterir. Hiçbir uygulama sonlandırılmaz.

- Hedef: Pardus 25 Xfce / X11 (Debian 13, Linux 6.12, systemd 257); GNOME desteği ek işlev
- Dil: Python 3 (servis, ajan, ölçüm, `nefes-baslat` sarmalayıcısı)
- Lisans (planlanan): GPL-3.0-or-later
- Ekip: Gültekin Erişik, Ali Osman Çıtak

> Durum: geliştirme aşamasında. Kurulum ve kullanım yönergeleri v0.5 (.deb) ile eklenecek.

Tasarım notları Obsidian vault'u olarak bu klasörde tutulur — Obsidian'da bu klasörü "Open folder as vault" ile açın, `notlar/00 Ana Sayfa.md` ile başlayın.
