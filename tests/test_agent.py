"""nefes_agent birim testleri — oturum ajanının mantığı (bildirim + "Devam ettir").

Bildirim gösterme ve D-Bus çağrısı dışarıdan verilir (sahte); gerçek Gio/libnotify bağlantısı
Pardus'ta uçtan uca denenir. Sözleşme: nefesd/tr.edu.bil461.Nefes1.xml (ADR-0003).
"""
from nefes_agent import Agent, display_name, frozen_message

MB = 1024 * 1024
APP = "/user.slice/user-1000.slice/user@1000.service/app.slice"
FIREFOX = f"{APP}/app-nefes-firefox-esr-1a2b3c4d.scope"
CALC = f"{APP}/app-nefes-libreoffice-5e6f7a8b.scope"


class FakeNotifier:
    def __init__(self):
        self.shown = {}  # anahtar -> (başlık, gövde)
        self.closed = []

    def show(self, key, summary, body, on_resume):
        self.shown[key] = (summary, body)
        self.on_resume = on_resume

    def close(self, key):
        self.closed.append(key)
        self.shown.pop(key, None)


class FakeResume:
    def __init__(self):
        self.calls = []

    def __call__(self, cgroup, done):
        self.calls.append(cgroup)
        self.done = done


def make():
    notifier, resume = FakeNotifier(), FakeResume()
    return Agent(notifier, resume), notifier, resume


# --- metin -------------------------------------------------------------------------

def test_display_name_uses_known_names_and_capitalises_others():
    assert display_name("firefox-esr") == "Firefox"
    assert display_name("libreoffice") == "LibreOffice"
    assert display_name("gimp") == "GIMP"
    assert display_name("e2e-hog") == "E2e-hog"


def test_frozen_message_matches_the_proposal_wording():
    assert frozen_message("firefox-esr", 423 * MB) == (
        "Firefox duraklatıldı",
        "Firefox, sistemin donmaması için geçici olarak duraklatıldı. 423 MB bellek boşaltılıyor.",
    )


def test_frozen_message_escapes_markup_in_app_names():
    summary, body = frozen_message("a<b>&c", 0)
    assert "<b>" not in body and "&lt;b&gt;&amp;c" in body
    assert "MB" not in body  # bellek bilinmiyorsa sayı yazılmaz


# --- olaylar ------------------------------------------------------------------------

def test_app_frozen_shows_one_notification_per_app():
    agent, notifier, _ = make()
    agent.on_frozen(FIREFOX, "firefox-esr", 423 * MB)
    agent.on_frozen(FIREFOX, "firefox-esr", 423 * MB)  # tekrar gelen sinyal kopya açmaz
    assert list(notifier.shown) == [FIREFOX]
    assert notifier.shown[FIREFOX][0] == "Firefox duraklatıldı"


def test_app_resumed_closes_that_apps_notification_only():
    agent, notifier, _ = make()
    agent.on_frozen(FIREFOX, "firefox-esr", MB)
    agent.on_frozen(CALC, "libreoffice", MB)
    agent.on_resumed(FIREFOX, "pressure_low")
    assert list(notifier.shown) == [CALC]


def test_app_resumed_for_an_unknown_app_does_nothing():
    agent, notifier, _ = make()
    agent.on_resumed(FIREFOX, "timeout")
    assert notifier.closed == []


# --- "Devam ettir" ------------------------------------------------------------------

def test_resume_button_calls_nefesd_with_the_cgroup():
    agent, notifier, resume = make()
    agent.on_frozen(FIREFOX, "firefox-esr", MB)
    notifier.on_resume()
    assert resume.calls == [FIREFOX]


def test_successful_resume_closes_the_notification():
    agent, notifier, resume = make()
    agent.on_frozen(FIREFOX, "firefox-esr", MB)
    notifier.on_resume()
    resume.done(True)
    assert FIREFOX not in notifier.shown


def test_failed_resume_closes_the_stale_notification():
    # false = nefesd bu uygulamayı artık dondurmuyor (zaten çözülmüş) → bildirim bayat
    agent, notifier, resume = make()
    agent.on_frozen(FIREFOX, "firefox-esr", MB)
    notifier.on_resume()
    resume.done(False)
    assert FIREFOX not in notifier.shown


def test_second_click_while_a_resume_is_pending_is_ignored():
    agent, notifier, resume = make()
    agent.on_frozen(FIREFOX, "firefox-esr", MB)
    notifier.on_resume()
    notifier.on_resume()
    assert resume.calls == [FIREFOX]


# --- yeniden senkronizasyon -----------------------------------------------------------

def test_sync_shows_frozen_apps_and_closes_the_rest():
    agent, notifier, _ = make()
    agent.on_frozen(CALC, "libreoffice", MB)  # artık donuk değil
    agent.sync([(FIREFOX, "firefox-esr", 30)])  # ListFrozen sonucu
    assert list(notifier.shown) == [FIREFOX]


def test_service_vanishing_closes_every_notification():
    agent, notifier, _ = make()
    agent.on_frozen(FIREFOX, "firefox-esr", MB)
    agent.on_frozen(CALC, "libreoffice", MB)
    agent.on_service_vanished()
    assert notifier.shown == {}


def test_agent_does_not_notify_when_notifications_are_disabled():
    notifier, resume = FakeNotifier(), FakeResume()
    enabled = [False]
    agent = Agent(notifier, resume, notifications_enabled=lambda: enabled[0])
    agent.on_frozen(FIREFOX, "firefox-esr", 423 * MB)
    agent.on_resumed(FIREFOX, "user")
    assert notifier.shown == {} and notifier.closed == []
    enabled[0] = True  # açılınca sonraki dondurma yine bildirilir
    agent.on_frozen(CALC, "libreoffice", 300 * MB)
    assert list(notifier.shown) == [CALC]
