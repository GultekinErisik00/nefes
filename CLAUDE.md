# Nefes — BİL461 İşletim Sistemleri Projesi

Pardus 25 için donma önleyici bellek baskısı yöneticisi: **öldürmek yerine dondur, belleği geri kazan, kullanıcının işini koru.**
Kaynak öneri belgesi: `Gultekin_Erisik_Ali_Osman_Citak_461_Proje_Onerisi.pdf` (tek doğruluk kaynağı; bu dosya onun çalışma özetidir).
Notlar bir Obsidian vault'u olarak tutulur: giriş noktası `notlar/00 Ana Sayfa.md`.

## Ekip
- **Gültekin Erişik** — nefesd (PSI izleme, karar motoru, eylem modülü), nefes-zram, systemd + .deb paketleme
- **Ali Osman Çıtak** — nefes-agent (bildirim + X11 odak izleme), nefes-baslat sarmalayıcısı, ölçüm araçları (nefes-olcum), pytest takımı
- Ortak: D-Bus sözleşmesi, ölçüm turları, demo/video/rapor

## Hedef platform
**Pardus 25 Xfce / X11** (Debian 13 trixie, Linux 6.12, systemd 257, Python 3.13) — asgari ürün Xfce, GNOME ek işlev (`notlar/05 Kararlar/ADR-0002 Asgari ürün Xfce.md`). Asgari çekirdek 5.19 (`memory.reclaim`). cgroup v2 + PSI zorunlu.
Geliştirme makinesi macOS'tur: **macOS'ta cgroup/PSI yoktur.** Çekirdek arayüzüne dokunan kod yalnızca Pardus 25 sanal makinesinde çalıştırılır.

**Uzak test makinesi: `ssh userpardus`** (VirtualBox, Pardus 25.2, kernel 6.12.95, kullanıcı `user` uid 1000). Ayrıntı ve güncel durum: `notlar/01 Proje/Test Ortamı.md`.
- Masaüstü **Xfce/X11** — uygulamalar `session-2.scope` içinde, pencere yöneticisiyle birlikte. **`session-*.scope` asla dondurulmaz.**
- `sudo` parola ister: ajan parola girmez; root gerektiren komutları kullanıcıya ver.
- Kod aktarımı: `rsync -a --exclude .git ./ userpardus:~/nefes/` (veya VM'de git clone).

## Planlanan depo yapısı
```
nefesd/            # sistem servisi (Python, root): psi.py, cgroups.py, karar.py, eylem.py, dbus_servis.py
nefes_agent/       # oturum ajanı: libnotify bildirimi + "Devam ettir" + X11 odak izleme (python-xlib)
nefes_baslat/      # uygulamaları systemd-run --user --scope ile kendi scope'unda başlatan sarmalayıcı + .desktop geçersiz kılmaları
nefes_zram/        # RAM'e göre /etc/systemd/zram-generator.conf yazar
nefes_olcum/       # gecikme probu, PSI kaydedici, yük senaryoları → CSV
tests/             # pytest; sahte cgroup ağacı (tmp_path) ile karar motoru testleri
debian/            # debhelper kaynak paketi, systemd birimleri, D-Bus policy
notlar/            # Obsidian vault notları (tasarım, çekirdek notları, haftalık günlük, kararlar)
```

## Güvenlik kuralları (pazarlık yok)
1. **Korunan liste asla dondurulmaz:** gnome-shell, Xwayland, PipeWire/WirePlumber, oturum yöneticisi, systemd birimleri. Aday yalnızca `user@UID.service/app.slice/*.scope`.
2. **Odaktaki uygulama asla dondurulmaz** (M6 ölçütü — birim testi zorunlu).
3. Her dondurmanın bir **güvenlik zamanlayıcısı** vardır; servis çökerse/durursa tüm dondurulmuş cgroup'lar çözülür (`ExecStopPost` + başlangıçta temizlik).
4. Çekirdek OOM killer devre dışı bırakılmaz; `oom_score_adj` ile oynanmaz.
5. Karar motoru saf fonksiyondur (girdi: cgroup anlık görüntüsü + odak + korunan liste → çıktı: eylem). Dosya sistemi erişimi ayrı modülde; böylece macOS'ta test edilebilir.
6. Gerçek `cgroup.freeze` / `memory.reclaim` yazan kod sadece VM'de denenir; host'ta asla.

## Kodlama kuralları
- Python 3.13, standart kütüphane + PyGObject (`gi.repository: Gio, GLib, Notify`). Ek PyPI bağımlılığı eklemeden önce sor (Debian paketlenebilirliği).
- Kod tanımlayıcıları İngilizce olabilir; **kullanıcıya görünen tüm metinler Türkçe**.
- PSI izleme `poll()` (POLLPRI) ile olay tabanlıdır; sürekli yoklama döngüsü yazma (M5: boşta CPU < %1).
- TDD: önce test (karar motoru, aday seçimi, zram boyutlandırma), sonra kod.
- Commit biçimi: `feat: …`, `fix: …`, `test: …`, `docs: …`.

## Başarı ölçütleri (özet)
M1 p99 gecikme < 500 ms, maks < 2 s · M2 toplam donma ≥ %80 azalma · M3 Seviye 3 olmadan 0 sonlandırma · M4 devam ettirme < 5 s · M5 CPU < %1, RSS < 30 MB · M6 korunan/odak testleri geçer. Ayrıntı: `notlar/01 Proje/Başarı Ölçütleri.md`.

## Not tutma kuralları (Obsidian)
- Yeni tasarım kararı → `notlar/05 Kararlar/` altında şablondan ADR; `notlar/05 Kararlar/Kararlar.md` dizinine ekle.
- Her çalışma oturumu sonunda → `notlar/04 Günlük/` haftalık notu güncelle (yapılan, sorun, sıradaki).
- Notlar arası bağlantı `[[wikilink]]`; frontmatter'da `tags`, `durum`, `sorumlu` alanları.
- Çekirdek arayüzü hakkında öğrenilen her somut bilgi (dosya biçimi, hata kodu, sürüm) → `notlar/03 Çekirdek/` ilgili not.

## Hangi skill ne zaman
| Durum | Skill / ajan |
|---|---|
| Yeni bileşen tasarımı | `superpowers:brainstorming` → `superpowers:writing-plans` |
| Kod yazma | `superpowers:test-driven-development` / `python-testing`, sonra `python-reviewer` ajanı |
| Hata ayıklama (VM'de) | `superpowers:systematic-debugging` |
| Çekirdek belgesi araştırması | `deep-research`, `documentation-lookup` |
| D-Bus arayüz tasarımı | `contract-first` |
| Mimari karar kaydı | `architecture-decision-records` |
| Vault'u bilgi grafiğine çevirme | `/graphify notlar` |
| Paketleme öncesi | `security-review` (root servis + D-Bus policy) |
| Teslim öncesi | `superpowers:verification-before-completion` |
