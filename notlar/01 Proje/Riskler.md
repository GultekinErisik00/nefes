---
tags: [nefes, risk]
---
# Riskler

| Risk | Etki | Önlem / B planı | Durum |
|---|---|---|---|
| Wayland'de odaktaki pencere alınamaz | Yüksek | GNOME Shell eklentisi → olmazsa Xfce `_NET_ACTIVE_WINDOW` → olmazsa korunan liste + "en son başlatılan" sezgisi | açık |
| Dondurulan uygulamada ağ zaman aşımı / görüntülü görüşme kopması | Orta | ses/görüntü akışı olanlar (PipeWire istemcileri) aday dışı; azami dondurma süresi; açık bildirim | açık |
| Swap yokken `memory.reclaim` yalnız sayfa önbelleği boşaltır | Orta | [[zram]] ön koşul; yoksa yalnız dondur + uyar | açık |
| Xfce'de uygulamalar ayrı cgroup'ta değil | Orta | asgari ürün GNOME; Xfce için `systemd-run --user --scope` sarmalayıcı | **gerçekleşti** (21 Kas, `userpardus` Xfce: tüm uygulamalar `session-2.scope`'ta) → [[Test Ortamı]] |
| Plan ~3 hafta geride (kod 21 Kas'ta sıfırdan) | Yüksek | 5–6. haftalara sıkıştırma, 12. hafta tamponu, kapsam daraltma sırası [[Takvim]]'de | açık |
| Yanlış süreç (gnome-shell) dondurulup oturum kilitlenir | **Yüksek** | yalnız `app.slice` scope'ları; kesin korunan liste; güvenlik zamanlayıcısı; birim testleri; yalnız VM | açık |
| VM sonuçları gerçek donanımı yansıtmaz | Orta | eski dizüstü; yoksa VM disk hızı kısıtlama | açık |
| Zaman yetersizliği | Orta | önce asgari ürün; 12. hafta tampon | açık |
