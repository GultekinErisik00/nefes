"""nefesd.gecmis.EventLog — son olayların halkası (D-Bus RecentEvents, arayüz 2026-11-25)."""
from nefesd.eylem import Event
from nefesd.gecmis import EventLog


def test_item_shape():
    log = EventLog(clock=lambda: 1700000000.7)
    log.record(Event("frozen", "/a/app-nefes-firefox-1.scope", "pressure", 5), "firefox")
    assert log.items() == ((1700000000, "frozen", "firefox", "pressure"),)


def test_keeps_last_20_newest_last():
    times = iter(range(100, 200))
    log = EventLog(clock=lambda: next(times))
    for i in range(25):
        log.record(Event("resumed", f"/p{i}", "user", 0), f"app{i}")
    items = log.items()
    assert len(items) == 20
    assert items[0][2] == "app5" and items[-1][2] == "app24"
