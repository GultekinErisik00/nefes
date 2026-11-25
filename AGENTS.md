# AGENTS.md — Nefes Proje Rehberi

**Nefes**, Pardus 25 (Xfce / X11) için donma önleyici bellek baskısı yöneticisidir (BİL461 İşletim Sistemleri dönem projesi).
Temel ilke: **öldürmek yerine dondur (`cgroup.freeze`), belleği zram'a geri kazan (`memory.reclaim`), kullanıcının işini koru.**

- **İletişim dili:** Kullanıcıya her zaman **Türkçe** yanıt ver; kullanıcıya görünen tüm arayüz, bildirim, CLI ve hata metinleri Türkçe olmalıdır.
- **Bilgi kaynağı:** Proje notları Obsidian vault olarak `notlar/` altındadır (`notlar/00 Ana Sayfa.md`). Mimari kararlar `notlar/05 Kararlar/` (ADR-0001..0004), ölçütler `notlar/01 Proje/Başarı Ölçütleri.md` içindedir.

---

## 1. Depo Yapısı

```text
nefesd/         # Bellek baskısı servisi (systemd kullanıcı servisi)
                #   psi.py (PSI ayrıştırma/tetikleyici), cgroups.py (cgroup v2 I/O),
                #   karar.py (saf karar motoru), eylem.py (Daemon çekirdeği),
                #   focus.py (X11 odak), gecmis.py (son 20 olay),
                #   dbus_servis.py + tr.edu.bil461.Nefes1.xml (D-Bus sözleşmesi)
nefes_agent/    # Oturum ajanı (tek örnekli Gtk.Application: tr.edu.bil461.NefesAgent)
                #   __init__.py (saf bildirim mantığı), istemci.py (Model + Gio D-Bus),
                #   simge.py (Ayatana panel simgesi), pencere.py (GTK 3 durum/ayar penceresi),
                #   gorunum.py (saf metin/sparkline), sistem.py (/proc/meminfo + zram)
nefes_ayar/     # ~/.config/nefes/ayarlar.ini okuma, atomik yazma, doğrulama
nefes_baslat/   # Uygulamaları systemd-run --user --scope ile kendi scope'unda başlatır
nefes_zram/     # RAM'e göre /etc/systemd/zram-generator.conf üretir
nefes_olcum/    # Gecikme probu, PSI kaydedici, M1/M2 özeti
data/           # .desktop dosyaları, SVG simgeler, systemd birimleri, çalıştırılabilir sarıcılar
debian/         # debhelper kaynak paketi (nefes 0.6.0)
deneyler/       # Çekirdek ve ölçüm Bash betikleri (VM'de çalıştırılır)
tests/          # pytest birim testleri (sahte cgroup ağacıyla) + tests/test_vm.py
notlar/         # Obsidian proje notları (Mimari, Çekirdek, Günlük, Kararlar, Deneyler)
```

---

## 2. Güvenlik ve Mimari Kurallar (Pazarlık Yok)

1. **Korunan liste ve kapsam sınırı:** Yalnızca `user@UID.service/app.slice/*.scope` altındaki kullanıcı uygulamaları aday olabilir. `session-*.scope`, masaüstü bileşenleri (`xfce4-panel`, `xfwm4`, `xfdesktop`, `xfce4-session`, `nefes-agent`, `pipewire`, `wireplumber`, `Xwayland`, `gnome-shell`) asla dondurulmaz.
2. **Odak koruması (M6):** Odaktaki uygulama asla dondurulmaz; odak bilinmiyorsa (`focus_known=False`) hiçbir şey dondurulmaz.
3. **Kullanıcı "asla dondurma" listesi:** Yerleşik `PROTECTED` listesine **yalnızca ekleme** yapar, onu daraltamaz; ayrılmış/aşırı genel adlar tüm sistemi koruma altına alıp Nefes'i etkisizleştirmemelidir.
4. **Güvenlik zamanlayıcısı ve temizlik:** Her dondurmanın `max_frozen_seconds` üst sınırı vardır. Servis durduğunda veya çöktüğünde tüm donuk uygulamalar çözülür (`Daemon.shutdown` + systemd `ExecStopPost=nefesd --thaw-all` + açılışta `startup()`).
5. **Çekirdek OOM killer:** Devre dışı bırakılmaz, `oom_score_adj` ile oynanmaz.
6. **D-Bus sözleşmesi (contract-first, ADR-0003 & ADR-0004):** Tek yetkili kaynak `nefesd/tr.edu.bil461.Nefes1.xml`'dir. Değişiklikler önce XML'de yapılır, geriye uyumlu (yalnızca ekleme) kalır. `nefes_agent`, `nefesd`'nin Python kodunu içe aktarmaz; arayüzü XML'den yükler.
7. **Ayar dosyası tek yazar ilkesi:** `~/.config/nefes/ayarlar.ini` dosyasına **yalnızca `nefes-agent`** atomik olarak yazar; `nefesd` yalnızca okur. Ayar hatası hiçbir koşulda servisi veya arayüzü çökertmemelidir.
8. **Saf mantık ayrımı:** `karar.py`, `eylem.py`, `nefes_agent/__init__.py`, `nefes_agent/gorunum.py`, `nefes_agent/istemci.py (Model)` dosya sistemine, GTK'ya ve D-Bus'a dokunmadan test edilebilir kalmalıdır.
9. **Olay tabanlı izleme (M5):** PSI izleme `poll()` + `POLLPRI` ile olay tabanlıdır; boşta sürekli yoklama yapılmaz (hedef: boşta CPU < %1, `nefesd` RSS < 30 MB). Simge yalnızca D-Bus sinyalleriyle güncellenir; `GetStatus` yalnızca pencere görünürken çağrılır.

---

## 3. Geliştirme ve Test Ortamı (macOS ↔ Pardus VM)

- **Geliştirme makinesi macOS'tur:** macOS'ta `pytest`, `cgroup v2`, `PSI`, `PyGObject/GTK` yoktur. Gerçek testler ve çekirdek/arayüz denemeleri **Pardus 25.2 VM (`ssh userpardus`, uid 1000, 2 GB RAM / 1 vCPU)** üzerinde yapılır (Tailscale açık olmalı).
- **Gerçek `cgroup.freeze` / `memory.reclaim` yalnızca VM'de çalıştırılır; host'ta asla.**
- **Kod aktarımı ve test:**
  ```bash
  rsync -a --exclude .git ./ userpardus:~/nefes/
  ssh userpardus 'cd ~/nefes && python3 -m pytest -q'
  ```
  *(VM entegrasyon testleri için: `NEFES_VM=1 python3 -m pytest -q tests/test_vm.py`)*
- **`sudo` ve parolalar:** Ajan asla parola girmez. `sudo` gerektiren komutları (ör. `.deb` kurulumu) kullanıcıya ver.
- **Uzak SSH süreç kuralları:**
  - `pkill -f "python3 -m nefesd"` SSH kabuğunun kendisini de öldürür → `pkill -f "^python3 -m nefesd"` kullan.
  - SSH içinde arka plan süreci başlatırken bağlantıyı açık bırakmamak için `setsid ... </dev/null >log 2>&1 &` kullan.
  - Ekran görüntüsü için `xfce4-screenshooter -f -s dosya.png` kullan.
  - İkinci bir `nefesd` başlatmadan önce kurulu `systemctl --user stop nefesd` ile çakışmayı önle.

---

## 4. Kodlama ve TDD Kuralları

- **Python 3.13:** 4 boşluk girinti, `snake_case` işlev/değişken, `PascalCase` sınıf, mevcut tip ek açıklamalarına (`from __future__ import annotations`) uyum.
- **Bağımlılık politikası:** Standart kütüphane + sistem PyGObject (`Gio`, `GLib`, `Gtk 3.0`, `Notify 0.7`, `AyatanaAppIndicator3 0.1`) ve `python3-xlib`. Debian paketlenebilirliği için kullanıcıya sormadan yeni PyPI bağımlılığı ekleme.
- **TDD:** Her yeni davranış ve hata düzeltmesi için önce başarısız olan birim testini yaz (`tests/test_*.py`), sonra en sade düzeltmeyi uygula ve VM'de tüm `pytest` takımını geçir. Sahte cgroup ağaçları için `tmp_path` kullan.
- **Güvenli metin:** GTK etiketlerinde `set_text` kullan, bildirim gövdesinde uygulama adlarını `html.escape` ile kaçır.

---

## 5. Git, Commit ve Not Tutma

- **Commit / Push:** Kullanıcı açıkça istemeden `git commit` veya `git push` yapma.
- **Commit biçimi:** Conventional Commit + kısa Türkçe özet (`feat: …`, `fix: …`, `test: …`, `docs: …`, `chore: …`).
- **Depoya asla eklenmeyecekler:** `HANDOFF.md`, `*_Proje_Onerisi.pdf`, `.superpowers/`, `.obsidian/` kişisel çalışma alanı dosyaları, `*.deb` / derleme artıkları.
- **Obsidian notları:**
  - Yeni mimari karar → `notlar/05 Kararlar/ADR-XXXX ….md` + `notlar/05 Kararlar/Kararlar.md` dizini.
  - Oturum/aşama sonu → `notlar/04 Günlük/` ilgili haftalık notu güncelle.
  - Yeni çekirdek bulgusu → `notlar/03 Çekirdek/` ilgili nota işle.
  - Ölçüm sonucu → `notlar/01 Proje/Başarı Ölçütleri.md` ve `notlar/06 Deneyler/`.
