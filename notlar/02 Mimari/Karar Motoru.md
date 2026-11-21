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

## Zorunlu birim testleri (M6)
- [ ] odaktaki uygulama en büyük olsa bile seçilmez
- [ ] korunan listedeki hiçbir şey seçilmez
- [ ] `app.slice` dışı cgroup seçilmez
- [ ] aday yoksa `NoOp`
- [ ] azami dondurma süresi dolan → `Thaw`
- [ ] odak donmuş uygulamaya geçerse → anında `Thaw`

Açık soru: Seviye 3 varsayılan açık mı kapalı mı? → [[Kararlar]]
