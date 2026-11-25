"""nefes_agent.istemci.Model — simge ve pencerenin gösterdiği durum (saf, arayüz 2026-11-25)."""
from nefes_agent.istemci import Model

MB = 1024 * 1024
FIREFOX = "/user.slice/user-1000.slice/user@1000.service/app.slice/app-nefes-firefox-esr-1a2b3c4d.scope"
CALC = "/user.slice/user-1000.slice/user@1000.service/app.slice/app-nefes-libreoffice-5e6f7a8b.scope"


def test_initial_model_is_service_down():
    model = Model()
    assert (model.service_up, model.enabled, model.level) == (False, True, "safe")
    assert model.frozen_rows(0.0) == []


def test_model_tracks_frozen_and_resumed():
    model = Model()
    model.on_appeared()
    model.on_frozen(FIREFOX, "firefox-esr", 420 * MB, now=100.0)
    model.on_frozen(CALC, "libreoffice", 300 * MB, now=110.0)
    model.on_resumed(FIREFOX)
    assert model.frozen_rows(130.0) == [(CALC, "libreoffice", 300 * MB, 20)]


def test_frozen_rows_report_elapsed_seconds_oldest_first():
    model = Model()
    model.on_frozen(CALC, "libreoffice", 300 * MB, now=110.0)
    model.on_frozen(FIREFOX, "firefox-esr", 420 * MB, now=100.0)
    assert [row[0] for row in model.frozen_rows(200.0)] == [FIREFOX, CALC]
    assert model.frozen_rows(200.0)[0][3] == 100


def test_sync_replaces_frozen_set_and_keeps_known_sizes():
    model = Model()
    model.on_frozen(FIREFOX, "firefox-esr", 420 * MB, now=100.0)
    model.on_frozen(CALC, "libreoffice", 300 * MB, now=100.0)
    model.sync([(FIREFOX, "firefox-esr", 30)], now=200.0)
    assert model.frozen_rows(200.0) == [(FIREFOX, "firefox-esr", 420 * MB, 30)]


def test_model_clears_on_vanished():
    model = Model()
    model.on_appeared()
    model.on_status(False, "high")
    model.on_frozen(FIREFOX, "firefox-esr", 420 * MB, now=100.0)
    model.on_vanished()
    assert model.service_up is False and model.frozen_rows(200.0) == []


def test_listeners_are_called_on_every_change():
    model = Model()
    calls = []
    model.subscribe(lambda: calls.append(1))
    model.on_appeared()
    model.on_status(True, "high")
    model.on_frozen(FIREFOX, "firefox-esr", 1, now=1.0)
    model.on_resumed(FIREFOX)
    model.on_vanished()
    assert len(calls) == 5
