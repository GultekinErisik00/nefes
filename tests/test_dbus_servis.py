"""dbus_servis testleri — sözleşme (XML) uyumu, uygulama adı ve özel veriyolunda uçtan uca.

Tek yetkili kaynak nefesd/tr.edu.bil461.Nefes1.xml'dir (ADR-0003). Buradaki beklenen imzalar
XML'den OKUNUR, elle yazılmaz: sözleşme değişip kod değişmezse bu testler kırılır.
"""
import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from nefesd.dbus_servis import (  # noqa: E402
    BUS_NAME,
    CONTRACT,
    INTERFACE,
    OBJECT_PATH,
    NefesService,
    app_name,
    signal_for,
)
from nefesd.eylem import Event  # noqa: E402

APP = "/user.slice/user-1000.slice/user@1000.service/app.slice"
FIREFOX = f"{APP}/app-nefes-firefox-11.scope"
CALC = f"{APP}/app-nefes-libreoffice-12.scope"


def contract_interface():
    node = Gio.DBusNodeInfo.new_for_xml(CONTRACT.read_text())
    return node.lookup_interface(INTERFACE)


def signature(args):
    return "(" + "".join(a.signature for a in args) + ")"


class FakeController:
    def __init__(self, frozen=None, resumable=()):
        self.frozen = dict(frozen or {})
        self.resumable = set(resumable)
        self.resumed = []

    def resume(self, path):
        self.resumed.append(path)
        return path in self.resumable

    def frozen_durations(self):
        return tuple(sorted(self.frozen.items()))


# --- uygulama adı ---------------------------------------------------------------

@pytest.mark.parametrize(
    "path, expected",
    [
        (FIREFOX, "firefox"),
        (CALC, "libreoffice"),
        (f"{APP}/app-nefes-e2e-hog-13667.scope", "e2e-hog"),
        (f"{APP}/app-nefes-test-1a2b3c4d.scope", "test"),  # systemd-run rastgele onaltılık son ek
        (f"{APP}/app-gnome-org.gnome.Nautilus-5678.scope", "org.gnome.Nautilus"),
        (f"{APP}/app-org.gnome.Terminal.slice/vte-spawn-3.scope", "vte-spawn"),
        (f"{APP}/run-u42.scope", "run-u42"),
        (f"{APP}/app-123.scope", "123"),  # asla boş değil
    ],
)
def test_app_name_extracts_a_short_display_name_from_the_scope(path, expected):
    assert app_name(path) == expected


# --- sözleşme uyumu (XML'e karşı) --------------------------------------------------

def test_contract_declares_exactly_the_members_the_service_implements():
    iface = contract_interface()
    assert iface is not None
    assert sorted(m.name for m in iface.methods) == sorted(NefesService.METHODS)
    assert sorted(s.name for s in iface.signals) == ["AppFrozen", "AppResumed"]


@pytest.mark.parametrize(
    "event",
    [
        Event("frozen", FIREFOX, "pressure", 501 * 1024 * 1024),
        Event("frozen", FIREFOX, "pressure", 0),
        Event("resumed", FIREFOX, "user", 0),
        Event("resumed", CALC, "pressure_low", 0),
    ],
)
def test_emitted_signal_matches_contract_signature(event):
    name, args = signal_for(event)
    declared = {s.name: s for s in contract_interface().signals}
    assert name in declared
    assert args.get_type_string() == signature(declared[name].args)


def test_contract_names_the_third_app_frozen_argument_memory_bytes():
    declared = {s.name: s for s in contract_interface().signals}
    assert [a.name for a in declared["AppFrozen"].args] == ["cgroup", "app_name", "memory_bytes"]


def test_frozen_signal_carries_path_name_and_memory_bytes():
    name, args = signal_for(Event("frozen", FIREFOX, "pressure", 1234))
    assert (name, args.unpack()) == ("AppFrozen", (FIREFOX, "firefox", 1234))


def test_resumed_signal_carries_path_and_reason():
    name, args = signal_for(Event("resumed", FIREFOX, "timeout", 0))
    assert (name, args.unpack()) == ("AppResumed", (FIREFOX, "timeout"))


def test_method_replies_match_contract_out_signatures():
    service = NefesService(FakeController(frozen={FIREFOX: 42.7}, resumable={FIREFOX}))
    declared = {m.name: m for m in contract_interface().methods}
    assert service.call("Resume", (FIREFOX,)).get_type_string() == signature(declared["Resume"].out_args)
    assert service.call("ListFrozen", ()).get_type_string() == signature(declared["ListFrozen"].out_args)


def test_list_frozen_reports_name_and_whole_seconds():
    service = NefesService(FakeController(frozen={FIREFOX: 42.7, CALC: 3.2}))
    assert service.call("ListFrozen", ()).unpack() == (
        [(FIREFOX, "firefox", 42), (CALC, "libreoffice", 3)],
    )


def test_resume_reports_controller_result():
    controller = FakeController(resumable={FIREFOX})
    service = NefesService(controller)
    assert service.call("Resume", (FIREFOX,)).unpack() == (True,)
    assert service.call("Resume", (CALC,)).unpack() == (False,)
    assert controller.resumed == [FIREFOX, CALC]


# --- özel test veriyolunda uçtan uca ------------------------------------------------

@pytest.fixture
def private_bus():
    bus = Gio.TestDBus.new(Gio.TestDBusFlags.NONE)
    bus.up()
    flags = (Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
             | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION)
    connect = lambda: Gio.DBusConnection.new_for_address_sync(bus.get_bus_address(), flags, None, None)  # noqa: E731
    server, client = connect(), connect()
    try:
        yield server, client
    finally:
        server.close_sync(None)
        client.close_sync(None)
        bus.down()


def run_until(done, timeout_s=3.0):
    """Ana bağlamı, done() doğru olana ya da süre dolana kadar döndürür."""
    ctx = GLib.MainContext.default()
    deadline = GLib.get_monotonic_time() + int(timeout_s * 1_000_000)
    while not done() and GLib.get_monotonic_time() < deadline:
        ctx.iteration(False)
    return done()


def call(client, server, method, args, reply_type):
    result = {}

    def finished(conn, res):
        result["value"] = conn.call_finish(res)

    client.call(server.get_unique_name(), OBJECT_PATH, INTERFACE, method, args,
                GLib.VariantType(reply_type), Gio.DBusCallFlags.NONE, 2000, None, finished)
    assert run_until(lambda: "value" in result)
    return result["value"].unpack()


def test_list_frozen_and_resume_work_over_a_real_bus(private_bus):
    server, client = private_bus
    controller = FakeController(frozen={FIREFOX: 10.0}, resumable={FIREFOX})
    NefesService(controller).export(server)
    assert call(client, server, "ListFrozen", None, "(a(ssu))") == ([(FIREFOX, "firefox", 10)],)
    assert call(client, server, "Resume", GLib.Variant("(s)", (FIREFOX,)), "(b)") == (True,)


def test_app_frozen_signal_reaches_a_subscriber(private_bus):
    server, client = private_bus
    service = NefesService(FakeController())
    service.export(server)
    received = []
    client.signal_subscribe(None, INTERFACE, "AppFrozen", OBJECT_PATH, None,
                            Gio.DBusSignalFlags.NONE,
                            lambda *a: received.append(a[5].unpack()))
    run_until(lambda: False, 0.2)  # abonelik veriyoluna ulaşsın
    service.emit(Event("frozen", FIREFOX, "pressure", 777))
    assert run_until(lambda: received)
    assert received == [(FIREFOX, "firefox", 777)]


def test_bus_name_constant_matches_contract_object_path():
    node = Gio.DBusNodeInfo.new_for_xml(CONTRACT.read_text())
    assert node.path == OBJECT_PATH
    assert BUS_NAME == "tr.edu.bil461.Nefes1"
