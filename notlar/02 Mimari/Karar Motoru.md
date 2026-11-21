---
tags: [nefes, mimari, nefesd]
sorumlu: Gültekin
test: Ali Osman
---
# Karar Motoru

**Saf fonksiyon** — dosya sistemine dokunmaz; macOS'ta pytest ile test edilir.

```python
decide(snapshot: list[AppCgroup], focus: str | None, protected: set[str],
       frozen: dict[str, float], pressure: PressureState, now: float) -> Action
```
- `AppCgroup`: `path`, `app_id` (scope adından: `app-gnome-firefox_firefox-1234.scope` → `firefox_firefox`), `memory_current`, `has_audio_video`
- `Action`: `NoOp` | `Freeze(path)` | `Thaw(path)` | `Throttle(path, high)` | `Kill(path)` (Seviye 3, yapılandırmayla)

## Aday kuralları
1. Yalnızca `.../user@UID.service/app.slice/` altındaki `*.scope` (ve isteğe bağlı `app-*.service`).
2. Korunan listede olan → ele (gnome-shell, Xwayland, pipewire, wireplumber, gnome-session, `*.service` sistem birimleri, nefes-agent'ın kendisi).
3. `focus` ile eşleşen cgroup → ele (**M6**).
4. Zaten donmuş → ele.
5. (ek) PipeWire akışı olan → ele.
6. Kalanlardan `memory_current` en büyük → aday. Eşitlikte en uzun süredir odakta olmayan.

## Kademeler
| Seviye | Koşul | Eylem |
|---|---|---|
| 1 (ek) | `some` baskı eşiği | arka plan uygulamalarına `memory.high` |
| 2 | tetikleyici | dondur + `memory.reclaim` |
| 3 | Seviye 2 sonrası N sn baskı sürüyor ve aday kalmadı | bildirerek en büyük donmuşu sonlandır (varsayılan: kapalı?) |

## Uygulama (2026-11-21) — `nefesd/karar.py`, testler `tests/test_karar.py` (35 test, TDD)
Gerçek arayüz yukarıdaki taslaktan sadeleşti:
```python
decide(snapshot: Snapshot, policy: Policy) -> tuple[Freeze | Thaw, ...]
Snapshot(apps, focus_path: str | None, focus_known: bool, pressure: Pressure, now: float)
AppCgroup(path, memory_current, frozen_since: float | None)   # path = /proc/PID/cgroup biçimi
Policy(uid, protected_names: frozenset[str], max_frozen_seconds, min_candidate_bytes)
Pressure: NORMAL | HIGH | SAFE
```
Tur sırası: önce zorunlu çözmeler (`focus`, `timeout`), sonra baskı eylemi (HIGH → en büyük adayı dondur; SAFE → en uzun donuk olanı çöz, turda tek). Seviye 1 (`memory.high`) ve Seviye 3 (sonlandırma) henüz yok.

**Kod incelemesi (python-reviewer) sonrası düzeltilenler:** yol doğrulaması regex yerine parça parça (`..`, `.`, satır sonu, ASCII dışı rakam, başka uid, scope içinde scope reddedilir); korunan ad app.slice altındaki **her** parçada aranır; `focus_known=False` → hiç dondurma yok; aynı yol iki kez gelirse tek eylem.

## Daemon'ın (eylem.py) üstlenmesi gerekenler — incelemeden
- [ ] **Zamanlayıcı:** PSI olay tabanlı → baskı yokken `decide` hiç çağrılmaz, `timeout` çözmesi kaçar. Donuk uygulama varken en yakın son tarihe göre uyanan bir zamanlayıcı şart.
- [ ] **Monoton saat:** `now`/`frozen_since` için `time.monotonic()`; duvar saati geri atlarsa çözme olmaz.
- [ ] **Bekleme süresi (cooldown):** zaman aşımıyla çözülen uygulama hemen yeniden dondurulabilir → toplam donukluk sınırsız. Son çözülme zamanını tutup N sn aday dışı bırak (AppCgroup'a alan eklenebilir).
- [ ] **Yeniden başlatma:** servis açılışta `cgroup.events` içinde `frozen 1` olan her şeyi çözmeli (frozen_since bilinmez).

## Zorunlu birim testleri (M6)
- [x] odaktaki uygulama en büyük olsa bile seçilmez (odak alt cgroup'ta olsa bile)
- [x] korunan listedeki hiçbir şey seçilmez
- [x] `app.slice` dışı cgroup seçilmez (`session-2.scope`, `session.slice`, benzer görünen sahte yol)
- [x] aday yoksa boş eylem
- [x] azami dondurma süresi dolan → `Thaw(timeout)` (yüksek baskıda bile)
- [x] odak donmuş uygulamaya geçerse → anında `Thaw(focus)`
- [x] baskı güvenli → en uzun donuk olan tek uygulama `Thaw(pressure_low)`

Açık soru: Seviye 3 varsayılan açık mı kapalı mı? → [[Kararlar]]
