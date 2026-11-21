---
tags: [nefes, mimari, dbus]
durum: taslak
sorumlu: ortak
hafta: 5
---
# D-Bus Sözleşmesi (TASLAK — hafta 5 çıktısı)

Ad ve yollar henüz kesin değil; ikiniz onaylayınca [[Kararlar]]'a ADR olarak işleyin.

- Veriyolu: **sistem** (nefesd root çalışır)
- Bus adı: `tr.edu.bil461.Nefes1` *(öneri)*
- Nesne yolu: `/tr/edu/bil461/Nefes1`
- Arayüz: `tr.edu.bil461.Nefes1.Manager`

## Yöntemler
| Yöntem | İmza | Kim çağırır | Not |
|---|---|---|---|
| `ReportFocus(s app_id, u pid)` | `su → ()` | nefes-agent (X11 odak) | servis pid → `/proc/PID/cgroup` ile cgroup'u kendisi çözer; **çağıranın UID'i ile cgroup sahibi eşleşmeli** |
| `Resume(s cgroup_id)` | `s → b` | nefes-agent | "Devam ettir"; yalnızca o oturumun sahibi |
| `ListFrozen()` | `→ a(sstt)` | ajan / ayarlar | (cgroup_id, app_name, frozen_since, bytes_reclaimed) |
| `GetStatus()` | `→ a{sv}` | ayarlar / ölçüm | psi avg10, seviye, donmuş sayısı |

## Sinyaller
| Sinyal | İmza | Anlam |
|---|---|---|
| `AppFrozen` | `(s cgroup_id, s app_name, u uid, t reclaimed_bytes)` | bildirim göster |
| `AppResumed` | `(s cgroup_id, s reason)` | reason: `user` / `pressure_low` / `timeout` / `focus` |
| `AppKilled` | `(s cgroup_id, s app_name)` | Seviye 3 |
| `PressureChanged` | `(u level)` | 0–3 |

## Güvenlik
- `/usr/share/dbus-1/system.d/tr.edu.bil461.Nefes1.conf`: sahiplik yalnız root; `send_destination` herkese açık ama her yöntem **çağıranın UID'ini** (`GetConnectionUnixUser`) doğrular.
- Bir kullanıcı başka kullanıcının uygulamasını devam ettiremez / odak bildiremez.
- Paketleme öncesi `security-review` skill'i ile gözden geçir.

## Açık sorular
- [ ] Bus adı / ters alan adı ne olsun?
- [ ] `app_name` çözümü: `.desktop` dosyasından mı (Gio.DesktopAppInfo) yoksa scope adından mı?
- [ ] Ajan sistem veriyolunu dinlerken sinyalleri UID'e göre filtrelemeli mi?
