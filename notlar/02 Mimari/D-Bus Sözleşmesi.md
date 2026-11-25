---
tags: [nefes, mimari, dbus]
durum: kabul
sorumlu: ortak
hafta: 5
---
# D-Bus Sözleşmesi

**Tek yetkili kaynak: `nefesd/tr.edu.bil461.Nefes1.xml`** — imzalar ve anlamlar orada; bu not şekli **kopyalamaz**, yalnızca bağlam ve gerekçe tutar. Karar: [[ADR-0003 D-Bus sözleşmesi]].

- Veriyolu: **oturum** · Bus adı `tr.edu.bil461.Nefes1` · Nesne `/tr/edu/bil461/Nefes1` · Arayüz `tr.edu.bil461.Nefes1.Manager`
- Sağlayıcı: nefesd (`nefesd/dbus_servis.py`) · Tüketici: nefes-agent (`nefes_agent/__main__.py`, XML'i `importlib.resources` ile yükler; 23 Kas'ta yazıldı, `deneyler/agent_e2e.sh` ile gerçek veriyolunda doğrulandı)
- Tüketici XML'i `Gio.DBusNodeInfo.new_for_xml` ile yükler; elle tip/alan kopyalamaz.
- Değişiklik protokolü: önce XML → iki taraf onayı → sonra kod.

## Nasıl denenir (Pardus)
```
bash deneyler/dbus_e2e.sh      # nefesd + gdbus introspect/monitor/call, baskı altında
gdbus call --session --dest tr.edu.bil461.Nefes1 --object-path /tr/edu/bil461/Nefes1 \
  --method tr.edu.bil461.Nefes1.Manager.ListFrozen
```

## Doğrulama
- `tests/test_dbus_servis.py`: sağlayıcının her sinyal/dönüş tipi XML'deki imzayla **otomatik** karşılaştırılır; XML'deki üye kümesi ile uygulanan küme birebir aynı olmalı; `Gio.TestDBus` özel veriyolunda çağrı + sinyal uçtan uca.
- 2026-11-23 gerçek oturum veriyolunda (`dbus_e2e.sh`): introspect XML ile aynı; `ListFrozen` ✅, `Resume` → `true` ve uygulama çözüldü ✅, tanımsız yol → `false` ✅, iki sinyal de yayınlandı ✅.

## ✅ Çözülen bulgu — sinyal sırası (2026-11-23)
Gerçek veriyolunda **`AppResumed` `AppFrozen`'dan ÖNCE geldi**: `AppFrozen`, arka plan geri kazanımı *bittiğinde* yayınlanıyordu (~1–3 s); kullanıcı bu arada "Devam ettir" dediyse ajan önce "çözüldü", sonra "donduruldu" görürdü → çalışan uygulama için eskimiş bildirim. Birim testleri bunu yakalayamadı (zamanlamaya bağlı).
**Düzeltme (sözleşme değişikliği, Gültekin onayı):** `AppFrozen` artık dondurma anında ana döngüden yayınlanıyor; üçüncü argüman `reclaimed_bytes` → **`memory_bytes`** (dondurma anındaki `memory.current`). Gerçekte geri kazanılan miktar yalnızca nefesd günlüğünde. XML'e sıra garantisi yazıldı; `test_resume_before_background_reclaim_keeps_frozen_then_resumed_order` hatayı yeniden üretiyor.
Yeniden test (`dbus_e2e.sh`): Resume dondurmadan 0,6 s sonra, geri kazanım bitmeden çağrıldı → sinyaller **AppFrozen → AppResumed** ✅. Bonus: bildirim artık geri kazanımı beklemeden anında çıkar.

## Kapanan açık sorular
- Bus adı → `tr.edu.bil461.Nefes1` (ADR-0003)
- `app_name` → scope adından (`app-nefes-firefox-11.scope` → `firefox`); `.desktop`'tan görünen ad ileride ajan tarafında zenginleştirilebilir.
- UID filtresi → oturum veriyolunda gerek yok; sistem veriyoluna geçilirse ADR-0003 yenilenir.
- `ReportFocus`, `GetStatus`, `AppKilled`, `PressureChanged` → asgari üründe yok (ADR-0003).
- **2026-11-25:** arayüz için `GetStatus`, `SetEnabled`, `ReloadSettings`, `RecentEvents` ve `StatusChanged` eklendi; `AppResumed.reason` += `"paused"` → [[ADR-0004 Arayüz ve sözleşme genişletmesi]]
