# Nefes Arayüzü (panel simgesi + durum/ayar penceresi) Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Amaç:** nefes-agent'a Ayatana panel simgesi ve GTK 3 durum/ayar penceresi eklemek; nefesd'ye ayar dosyası, duraklatma, olay geçmişi ve durum sinyali kazandırmak.

**Mimari:** Ortak saf `nefes_ayar` paketi `~/.config/nefes/ayarlar.ini`'yi okur/yazar (tek yazar: ajan). nefesd ayarları açılışta ve `ReloadSettings`'te uygular; D-Bus sözleşmesine yalnızca ekleme yapılır. nefes-agent `Gtk.Application` olur; tüm biçimlendirme/durum mantığı saf modüllerde, GTK kodu ince.

**Teknoloji:** Python 3.13, PyGObject (Gtk 3.0, Gio, GLib, Notify 0.7, AyatanaAppIndicator3 0.1), pytest, debhelper.

**Spec:** `docs/superpowers/specs/2026-11-25-nefes-arayuz-design.md`

## Genel kısıtlar
- Yeni PyPI bağımlılığı yok; yalnızca standart kütüphane + PyGObject.
- Kullanıcıya görünen tüm metinler Türkçe.
- D-Bus sözleşmesi (`nefesd/tr.edu.bil461.Nefes1.xml`) önce değişir; **yalnızca ekleme**, mevcut üyeler aynen kalır.
- nefes-agent nefesd kodunu içe aktarmaz (yalnızca XML + `nefes_ayar` + `nefes_baslat.menu_apps`).
- Karar motoru (`nefesd/karar.py`) saf kalır, imzası değişmez.
- Kullanıcının "asla dondurma" listesi yerleşik `PROTECTED`'a **eklenir**, onu asla daraltmaz.
- Pencere kapalıyken yoklama yok; simge yalnızca sinyallerle güncellenir.
- Ayar dosyasına yalnızca ajan yazar; yazma atomik (`tempfile` + `os.replace`).
- Komut satırında açıkça verilen `--stall-ms` / `--max-frozen` dosyadan önceliklidir.
- Testler Pardus'ta çalışır (Mac'te pytest yok): `rsync -a --exclude .git --exclude '*_Proje_Onerisi.pdf' ./ userpardus:~/nefes/ && ssh userpardus 'cd ~/nefes && python3 -m pytest -q'`. Gerçek GTK/cgroup yalnızca VM'de.
- Commit yalnızca kullanıcı isteyince; biçim `feat: …` / `test: …` / `docs: …`.

## İnceleme odağı
1. **Elle bozulmuş ayar dosyası** (bilinmeyen anahtar, `hassasiyet = cokcok`, `en_uzun_donma_dk = abc`, ikili çöp) → o alan varsayılan, uyarı listesi dolu, istisna yok. *(Görev 1)*
2. **`asla_dondurma` içinde boş/yalnızca noktalama öğesi** (`asla_dondurma = , ,!`) → atılır; boş alt dize her scope'la eşleşip Nefes'i sessizce kapatırdı. *(Görev 1)*
3. **Duraklatılmışken nefesd yeniden başlar** → `etkin = false` okunur, baskıda dondurma yok. *(Görev 4)*
4. **Donuk uygulama varken Duraklat** → hepsi `reason="paused"` ile çözülür; sonra eski bildirimden gelen `Resume` `False` döner, hata yok. *(Görev 2)*
5. **Ajan nefesd'den önce başlar ya da nefesd düşer** → simge "Nefes çalışmıyor", donuk listesi boş. *(Görev 5, Görev 6)*

---

### Görev 1: `nefes_ayar` — ayar dosyası

**Dosyalar:**
- Oluştur: `nefes_ayar/__init__.py`
- Test: `tests/test_ayar.py`
- Değiştir: `debian/nefes.install` (mevcut `nefesd`/`nefes_agent` satırlarının düzeniyle `nefes_ayar` ekle)

**Arayüzler — üretir:**
- `SENSITIVITY_STALL_MS: dict[str, int] = {"az": 500, "orta": 300, "cok": 200}`
- `MAX_FROZEN_CHOICES_MIN: tuple[int, ...] = (5, 10, 20, 30)`
- `@dataclass(frozen=True) class Settings`: `enabled: bool = True`, `sensitivity: str = "orta"`, `max_frozen_min: int = 10`, `never_freeze: tuple[str, ...] = ()`, `notifications: bool = True`; özellikler `stall_ms -> int`, `max_frozen_seconds -> float`
- `config_path(env: Mapping[str, str] = os.environ) -> Path` → `$XDG_CONFIG_HOME/nefes/ayarlar.ini`, yoksa `$HOME/.config/nefes/ayarlar.ini`
- `normalize_name(name: str) -> str` → `nefes_baslat.unit_name` kuralı: küçük harf, `[^a-z0-9]+` → `-`, kenar `-` kırpılır
- `load(path: Path) -> tuple[Settings, tuple[str, ...]]` → (ayarlar, Türkçe uyarılar); dosya yoksa `(Settings(), ())`
- `save(path: Path, settings: Settings) -> None` → atomik, dizini oluşturur
- `validate(settings: Settings) -> str | None` → geçersizse Türkçe neden

- [ ] **Adım 1: Başarısız testleri yaz** (`tests/test_ayar.py`)
  - `test_missing_file_gives_defaults`: `load(tmp_path / "yok.ini") == (Settings(), ())`
  - `test_roundtrip`: `Settings(False, "cok", 20, ("vlc", "thunderbird"), False)` → `save` → `load` aynı ayar, uyarı yok
  - `test_sensitivity_maps_to_stall_ms`: az→500, orta→300, cok→200; `Settings().max_frozen_seconds == 600.0`
  - `test_bad_field_falls_back_per_field` (parametrize: `hassasiyet = cokcok`, `en_uzun_donma_dk = abc`, `en_uzun_donma_dk = 7`, `etkin = belki`) → yalnız o alan varsayılan, diğer alanlar korunur, `len(uyarılar) == 1`
  - `test_unknown_keys_and_sections_are_ignored` → uyarı yok
  - `test_unreadable_file_gives_defaults_with_warning`: `b"\xff\xfe\x00["` → `Settings()` ve 1 uyarı
  - `test_never_freeze_is_normalized_and_drops_empty`: `asla_dondurma = VLC, , !, Mozilla Thunderbird,vlc` → `("vlc", "mozilla-thunderbird")`
  - `test_save_is_atomic_and_leaves_no_temp_files`: kaydet sonrası dizinde yalnız `ayarlar.ini`
  - `test_config_path_honours_xdg`: `{"XDG_CONFIG_HOME": "/x", "HOME": "/h"}` → `/x/nefes/ayarlar.ini`; `{"HOME": "/h"}` → `/h/.config/nefes/ayarlar.ini`
  - `test_validate_rejects_unknown_choices`: `Settings(sensitivity="x")`, `Settings(max_frozen_min=7)` → str; `Settings()` → `None`
- [ ] **Adım 2: Kırmızıyı gör** — `python3 -m pytest tests/test_ayar.py -q` → toplama hatası (`nefes_ayar` yok)
- [ ] **Adım 3: Uygula** — `configparser` (`interpolation=None`, `inline_comment_prefixes=(";", "#")`), bölüm `[nefes]`, anahtarlar `etkin`, `hassasiyet`, `en_uzun_donma_dk`, `asla_dondurma`, `bildirim`. Boolean kabul: `true/false/evet/hayır/1/0`.
- [ ] **Adım 4: Yeşili gör** — aynı komut
- [ ] **Adım 5: Commit (kullanıcı isterse)** — `feat: nefes_ayar — kullanıcı ayar dosyası`

### Görev 2: nefesd çekirdeği — duraklatma, yeniden yapılandırma, durum, olay geçmişi

**Dosyalar:**
- Değiştir: `nefesd/eylem.py`
- Oluştur: `nefesd/gecmis.py`
- Test: `tests/test_eylem.py`, `tests/test_gecmis.py`

**Arayüzler:**
- Tüketir: mevcut `Daemon`, `Config`, `Event`, `psi.classify` / `Pressure`
- Üretir:
  - `Daemon.__init__(…, on_status: Callable[[bool, str], None] | None = None, enabled: bool = True)`
  - `Daemon.set_enabled(enabled: bool) -> None` — `False`: donuk her şey `_thaw(path, "paused", now)`; sonraki `tick`'ler karar motorunu çağırmaz, `()` döner. Değer değişince `on_status(enabled, level)`.
  - `Daemon.reconfigure(config: Config) -> None` — sonraki `tick`'ten itibaren geçerli; donuk uygulamalar korunur.
  - `Daemon.status() -> tuple[bool, str, float]` — `(enabled, level, son some_avg10)`; `level ∈ {"safe", "normal", "high"}` (`Pressure` üyesinin küçük harfli adı); hiç tick yoksa `"safe", 0.0`.
  - `tick` seviyeyi her çağrıda hesaplar; öncekinden farklıysa `on_status(enabled, level)`.
  - `gecmis.py`: `class EventLog(clock: Callable[[], float] = time.time, maxlen: int = 20)`; `record(event: Event, app_name: str) -> None`; `items() -> tuple[tuple[int, str, str, str], ...]` = `(int(unix), kind, app_name, reason)`, en yeni sonda; `frozen` olaylarının reason'ı `"pressure"`.

- [ ] **Adım 1: Başarısız testler** (mevcut `test_eylem.py` sahte Ops/saat düzeniyle)
  - `test_pause_thaws_everything_with_reason_paused` → thaw çağrıldı, `Event("resumed", p, "paused", 0)` bildirildi
  - `test_paused_daemon_never_freezes_under_pressure`: `set_enabled(False)`; `tick(True, 80.0) == ()`, freeze yok
  - `test_resume_after_pause_returns_false` (İnceleme odağı 4)
  - `test_reenabled_daemon_freezes_again`
  - `test_daemon_created_disabled_does_not_freeze`: `Daemon(…, enabled=False)`
  - `test_on_status_called_on_enable_change_and_level_change_only`: aynı seviyede iki tick → 1 çağrı; seviye değişimi → 2; `set_enabled(False)` → 3
  - `test_status_reports_last_level_and_avg10`
  - `test_reconfigure_applies_new_max_frozen`: 600→60 s; saat 61 s ilerleyince `timeout` ile çözülür
  - `tests/test_gecmis.py`: `test_keeps_last_20_newest_last`, `test_item_shape` → `(1700000000, "frozen", "firefox", "pressure")`
- [ ] **Adım 2: Kırmızıyı gör** — `python3 -m pytest tests/test_eylem.py tests/test_gecmis.py -q`
- [ ] **Adım 3: Uygula**
- [ ] **Adım 4: Yeşili gör** — tüm takım `python3 -m pytest -q`
- [ ] **Adım 5: Commit (kullanıcı isterse)** — `feat: nefesd duraklatma, yeniden yapılandırma ve olay geçmişi`

### Görev 3: D-Bus sözleşmesi genişletmesi + ADR-0004

**Dosyalar:**
- Değiştir: `nefesd/tr.edu.bil461.Nefes1.xml`, `nefesd/dbus_servis.py`, `notlar/05 Kararlar/Kararlar.md`, `notlar/02 Tasarım/D-Bus Sözleşmesi.md`
- Oluştur: `notlar/05 Kararlar/ADR-0004 Arayüz ve sözleşme genişletmesi.md` (ADR şablonundan)
- Test: `tests/test_dbus_servis.py`

**Arayüzler — üretir:**
- XML'e: `GetStatus() → (b enabled, s pressure_level, d some_avg10)`; `SetEnabled(b enabled) → ()`; `ReloadSettings() → (b ok, s message)`; `RecentEvents() → a(tsss) events`; sinyal `StatusChanged(b enabled, s pressure_level)`. Yorum bloğuna `pressure_level` değerleri (`"safe" | "normal" | "high"`) ve `AppResumed.reason` için `"paused"`.
- `Controller` protokolüne: `status() -> tuple[bool, str, float]`, `set_enabled(enabled: bool) -> None`, `reload_settings() -> tuple[bool, str]`, `recent_events() -> tuple[tuple[int, str, str, str], ...]`
- `NefesService.emit_status(enabled: bool, level: str) -> None`

- [ ] **Adım 1: Başarısız testler** (mevcut `Gio.TestDBus` düzeni)
  - `test_contract_declares_new_members`: dört yöntem + `StatusChanged`, imzalar yukarıdaki gibi
  - `test_get_status_over_bus` → `(True, "normal", 12.5)`
  - `test_set_enabled_forwards_to_controller`
  - `test_reload_settings_returns_ok_and_message` → sahte `(False, "hassasiyet geçersiz")` aynen gelir
  - `test_recent_events_over_bus` → `[(1700000000, "frozen", "firefox", "pressure")]`
  - `test_status_changed_signal_is_received`
  - Mevcut Resume/ListFrozen testleri değişmeden geçer
- [ ] **Adım 2: Kırmızıyı gör** — `python3 -m pytest tests/test_dbus_servis.py -q`
- [ ] **Adım 3: Uygula** — önce XML, sonra `call` dalları ve `emit_status`
- [ ] **Adım 4: Yeşili gör** — tüm takım
- [ ] **Adım 5: ADR-0004** (bağlam: günlük kullanım arayüzü; karar: ekleme-only genişletme, tek yazarlı ayar dosyası, Ayatana + ajan içinde; sonuçlar: ajan GTK yükler, sözleşme geriye uyumlu); Kararlar dizinine ve D-Bus Sözleşmesi notuna `[[wikilink]]`
- [ ] **Adım 6: Commit (kullanıcı isterse)** — `feat: D-Bus sözleşmesi — durum, duraklatma, ayar yenileme, olay geçmişi (ADR-0004)`

### Görev 4: nefesd bağlantısı — ayarlar, yeniden yükleme, komut satırı önceliği

**Dosyalar:**
- Değiştir: `nefesd/__main__.py`
- Test: `tests/test_main.py`

**Arayüzler:**
- Tüketir: `nefes_ayar.load/validate/config_path/Settings`; Görev 2 eklemeleri ve `EventLog`; Görev 3 `Controller` protokolü ve `emit_status`
- Üretir:
  - `parse_args`: `--stall-ms`, `--max-frozen` varsayılanı `None`; yeni `--settings PATH` (varsayılan `nefes_ayar.config_path()`)
  - `effective(args: argparse.Namespace, settings: Settings) -> tuple[int, float, frozenset[str]]` → `(stall_ms, max_frozen_seconds, PROTECTED | set(settings.never_freeze))`; komut satırı değeri varsa o
  - `class Controller` (`__main__.py`): kilitli daemon + `EventLog` + yeniden yükleme; Görev 3 protokolünü uygular. `reload_settings()`: oku → `validate` → geçersizse `(False, neden)`, eski ayar kalır; geçerliyse `daemon.reconfigure(...)`, `daemon.set_enabled(settings.enabled)`, stall değiştiyse `rearm_requested` bayrağı → `(True, "")`.
  - Ana döngü `rearm_requested` görünce PSI fd'sini kapatıp yeni `trigger_line(...)` ile açar ve `poller`'a yeniden kaydeder.

- [ ] **Adım 1: Başarısız testler**
  - `test_effective_uses_settings_when_cli_not_given`: `Settings(sensitivity="az", max_frozen_min=20, never_freeze=("vlc",))` → `(500, 1200.0, PROTECTED | {"vlc"})`
  - `test_cli_overrides_settings`: `--stall-ms 150 --max-frozen 60` → `(150, 60.0, …)`
  - `test_never_freeze_only_adds_to_protected`
  - `test_reload_invalid_keeps_previous_settings` → `(False, str)`, politika değişmedi
  - `test_reload_valid_reconfigures_and_requests_rearm_when_stall_changes`
  - `test_startup_with_disabled_settings_does_not_freeze` (İnceleme odağı 3)
- [ ] **Adım 2: Kırmızıyı gör** — `python3 -m pytest tests/test_main.py -q`
- [ ] **Adım 3: Uygula** — `build_daemon` ayarları alır; `run` içinde `EventLog` notify dinleyicisi, `on_status` → `service.emit_status`; ayar uyarıları `log.warning`
- [ ] **Adım 4: Yeşili gör** — tüm takım
- [ ] **Adım 5: VM'de doğrula** — `systemctl --user restart nefesd`; `gdbus call --session --dest tr.edu.bil461.Nefes1 --object-path /tr/edu/bil461/Nefes1 --method tr.edu.bil461.Nefes1.Manager.GetStatus` → `(true, 'safe', …)`; dosyaya `etkin = false` + `ReloadSettings` → `(true, '')`; `GetStatus` → `false`; günlük hatasız
- [ ] **Adım 6: Commit (kullanıcı isterse)** — `feat: nefesd ayar dosyasını uygular ve yeniden yükler`

### Görev 5: Ajanın saf görünüm mantığı

**Dosyalar:**
- Oluştur: `nefes_agent/gorunum.py`, `nefes_agent/sistem.py`
- Değiştir: `nefes_agent/__init__.py`
- Test: `tests/test_gorunum.py`, `tests/test_sistem.py`, `tests/test_agent.py`

**Arayüzler — üretir:**
- `gorunum.py`:
  - `LEVEL_TEXT = {"safe": "düşük", "normal": "orta", "high": "yüksek"}`
  - `REASON_TEXT = {"pressure": "baskı yüksek", "user": "sen", "focus": "odaklandın", "timeout": "süre doldu", "pressure_low": "baskı azaldı", "paused": "duraklatıldı", "shutdown": "Nefes kapandı"}`; bilinmeyen → `"çözüldü"`
  - `tray_state(service_up: bool, enabled: bool, level: str, frozen_count: int) -> tuple[str, str]` → (simge, ipucu). Simgeler `nefes-kapali`, `nefes-duraklatildi`, `nefes-donuk`, `nefes-baski`, `nefes-normal`; öncelik bu sırayla (çalışmıyor > duraklatıldı > donuk > `level == "high"` > normal). İpuçları: `"Nefes çalışmıyor"`, `"Nefes duraklatıldı"`, `"Nefes açık — 2 uygulama donduruldu"`, `"Nefes açık — baskı yüksek"`, `"Nefes açık — baskı düşük"`
  - `format_mb(nbytes: int) -> str` (`"420 MB"`; ≥ 1024 MB → `"1,4 GB"`)
  - `format_duration(seconds: int) -> str` (`"40 sn"`, `"3 dk"`, `"1 sa 5 dk"`)
  - `event_line(when: int, kind: str, app_name: str, reason: str, tz: tzinfo | None = None) -> str` → `"14:02 Firefox donduruldu (baskı yüksek)"`, `"13:40 Calc devam ettirildi (sen)"` (ad `display_name` ile)
  - `sparkline(values: Sequence[float], width: int = 60) -> str` (son `width` değer, `▁▂▃▄▅▆▇█`, 0–100 ölçeği; boşsa `""`)
- `sistem.py`: `parse_meminfo(text: str) -> tuple[int, int]` (kullanılan = MemTotal − MemAvailable, toplam; bayt); `parse_mm_stat(text: str) -> tuple[int, int] | None` (orig_data_size, mem_used_total; bozuksa `None`); `read_memory(proc: Path = Path("/proc"), sys: Path = Path("/sys")) -> tuple[tuple[int, int], tuple[int, int] | None]`
- `Agent.__init__(…, notifications_enabled: Callable[[], bool] = lambda: True)`: `False` iken `on_frozen` bildirim göstermez, izlemeye devam eder

- [ ] **Adım 1: Başarısız testler**
  - `tray_state` tablosu (parametrize; İnceleme odağı 5: `(False, True, "high", 2)` → `("nefes-kapali", "Nefes çalışmıyor")`)
  - `format_mb`, `format_duration`, `event_line` (`tz=timezone.utc`), `sparkline` örnekleri
  - `parse_meminfo` gerçek biçimde örnekle; `parse_mm_stat("325058560 99614720 104857600 0 104857600 0 0 0 0") == (325058560, 104857600)`; `parse_mm_stat("") is None`
  - `test_agent_tracks_but_does_not_notify_when_disabled`
- [ ] **Adım 2: Kırmızıyı gör** — `python3 -m pytest tests/test_gorunum.py tests/test_sistem.py tests/test_agent.py -q`
- [ ] **Adım 3: Uygula**
- [ ] **Adım 4: Yeşili gör** — tüm takım
- [ ] **Adım 5: Commit (kullanıcı isterse)** — `feat: nefes-agent görünüm mantığı`

### Görev 6: Ajan GTK katmanı — uygulama, simge, pencere

**Dosyalar:**
- Değiştir: `nefes_agent/__main__.py`
- Oluştur: `nefes_agent/istemci.py`, `nefes_agent/simge.py`, `nefes_agent/pencere.py`
- Test: `tests/test_istemci.py` (saf `Model`); GTK elle doğrulanır

**Arayüzler:**
- Tüketir: Görev 3 sözleşmesi, Görev 1 `nefes_ayar`, Görev 5 `gorunum`/`sistem`, mevcut `Agent`/`LibnotifyNotifier`, `nefes_baslat.menu_apps`/`SOURCE_DIRS`
- Üretir:
  - `istemci.py`: `class Model` (saf): `service_up: bool`, `enabled: bool`, `level: str`, `frozen: dict[str, tuple[str, int, float]]` (cgroup → ad, bayt, monoton donma anı); `on_frozen(cgroup, name, nbytes, now)`, `on_resumed(cgroup)`, `on_status(enabled, level)`, `on_vanished()`, `sync(apps, now)`; `frozen_rows(now: float) -> list[tuple[str, str, int, int]]` (cgroup, ad, bayt, geçen saniye). `class NefesClient`: tek `Gio.DBusProxy` (sözleşme XML'inden), asenkron `resume`, `list_frozen`, `get_status`, `set_enabled`, `reload_settings`, `recent_events` (her biri `done` geri çağrısı), sinyalleri `Model`'e ve dinleyicilere iletir, `bus_watch_name` ile appeared/vanished.
  - `simge.py`: `Tray.create(model, client, show_window) -> Tray | None` — `AyatanaAppIndicator3` yoksa `None` + uyarı; `refresh()` simge, ipucu ve menüyü (`tray_state`, `frozen_rows`) yeniden kurar.
  - `pencere.py`: `class Window(Gtk.ApplicationWindow)` — spec taslağındaki dört bölüm; `delete-event` → gizle; görünürken `GLib.timeout_add_seconds(2, …)` ile `get_status` + `read_memory`, gizlenince kaldır; ayar değişikliği → `nefes_ayar.save` → `reload_settings`, `ok=False` ise önceki `Settings` geri yazılır ve `Gtk.InfoBar`'da mesaj; Duraklat/Sürdür → `save(enabled=…)` → `set_enabled`; "+ Ekle" `menu_apps` listesinden seçtirir, kaydın `Exec` programının taban adı `normalize_name` ile eklenir; tüm etiketler `set_text`.
  - `__main__.py`: `Gtk.Application(application_id="tr.edu.bil461.NefesAgent", flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)`; `--pencere` → pencereyi göster; birincil örnek `hold()` ile pencere yokken yaşar; SIGTERM/SIGINT'te bildirimler kapanır ve çıkılır (bugünkü davranış).

- [ ] **Adım 1: Başarısız testler** (`tests/test_istemci.py`): `test_model_tracks_frozen_and_resumed`, `test_model_clears_on_vanished`, `test_frozen_rows_report_elapsed_seconds`, `test_sync_replaces_frozen_set`
- [ ] **Adım 2: Kırmızıyı gör** — `python3 -m pytest tests/test_istemci.py -q`
- [ ] **Adım 3: Uygula** `Model`, sonra GTK sınıfları
- [ ] **Adım 4: Yeşili gör** — tüm takım
- [ ] **Adım 5: VM'de elle doğrula** (`systemctl --user stop nefes-agent`, sonra masaüstü oturumunda `python3 -m nefes_agent`) ve ekran görüntüsü al:
  - panelde simge, ipucu "Nefes açık — baskı düşük"
  - `stress-ng --vm 1 --vm-bytes 1500M --vm-keep --timeout 60s` sırasında simge "donuk", menüde uygulama + "Devam ettir" çalışır
  - `python3 -m nefes_agent --pencere` pencereyi öne getirir, ikinci süreç kalmaz
  - pencere kapatılınca süreç sürer; gizliyken `top` CPU ≈ %0
  - Duraklat → simge "duraklatıldı", `~/.config/nefes/ayarlar.ini` içinde `etkin = false`
  - `systemctl --user stop nefesd` → simge "Nefes çalışmıyor", pencerede düğmeler pasif
- [ ] **Adım 6: Commit (kullanıcı isterse)** — `feat: nefes-agent panel simgesi ve durum/ayar penceresi`

### Görev 7: Paketleme, belgeler, ölçüm

**Dosyalar:**
- Oluştur: `data/applications/nefes.desktop` (`Name=Nefes`, `Comment=Bellek baskısı yöneticisi`, `Exec=nefes-agent --pencere`, `Icon=nefes-normal`, `Categories=System;Settings;`), `data/icons/nefes-{kapali,duraklatildi,normal,baski,donuk}.svg`
- Değiştir: `debian/control` (Depends `gir1.2-gtk-3.0`; Recommends `gir1.2-ayatanaappindicator3-0.1`), `debian/nefes.install`, `debian/changelog` (0.6.0), `README.md` (arayüz bölümü), `notlar/02 Tasarım/Bileşenler.md`, `notlar/01 Proje/Başarı Ölçütleri.md` (M5'e ajan RSS notu), `notlar/04 Günlük/` haftalık not, spec'e plan bağlantısı

- [ ] **Adım 1: Dosyaları ekle**; VM'de `desktop-file-validate data/applications/nefes.desktop` → çıktı yok
- [ ] **Adım 2: Paketi derle** — VM'de `dpkg-buildpackage -us -uc -b` → `../nefes_0.6.0_all.deb`; `lintian` yeni hata yok
- [ ] **Adım 3: Kur** (kullanıcı terminalinde) — `sudo apt install ../nefes_0.6.0_all.deb`, `nefes-oturum`; menüde "Nefes" pencereyi açar; `grep -c X-Nefes-Baslat ~/.local/share/applications/nefes.desktop` → dosya yok ya da 0 (sarmalanmamış)
- [ ] **Adım 4: M5'i yeniden ölç** — `bash deneyler/m5_maliyet.sh`: nefesd boşta CPU < %1, RSS < 30 MB; ajanın VmRSS'i ayrıca not edilir
- [ ] **Adım 5: Belgeleri güncelle**
- [ ] **Adım 6: Commit (kullanıcı isterse)** — `feat: nefes 0.6.0 — arayüz paketi`
