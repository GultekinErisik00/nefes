"""Karar motoru birim testleri (M6: korunan liste ve odak asla dondurulmaz).

Yollar /proc/<pid>/cgroup biçimindedir (cgroup köküne göre, baştaki "/" ile).
Beklenen değerler elle yazılmış sabitlerdir; karar motorunun kendisinden türetilmez.
"""
import pytest

from nefesd.karar import AppCgroup, Freeze, Policy, Pressure, Snapshot, Thaw, decide

MB = 1024 * 1024
APP_SLICE = "/user.slice/user-1000.slice/user@1000.service/app.slice"
FIREFOX = f"{APP_SLICE}/app-nefes-firefox-11.scope"
CALC = f"{APP_SLICE}/app-nefes-libreoffice-12.scope"
TERMINAL = f"{APP_SLICE}/app-nefes-xfce4-terminal-13.scope"
PANEL = f"{APP_SLICE}/app-nefes-xfce4-panel-14.scope"
XFCE_SESSION = "/user.slice/user-1000.slice/session-2.scope"
PIPEWIRE = "/user.slice/user-1000.slice/user@1000.service/session.slice/pipewire.service"

POLICY = Policy(
    uid=1000,
    protected_names=frozenset({"xfce4-panel", "xfwm4", "pipewire", "nefes-agent"}),
    max_frozen_seconds=600.0,
    min_candidate_bytes=50 * MB,
)
NOW = 10_000.0


def app(path: str, mb: int, frozen_since: float | None = None) -> AppCgroup:
    return AppCgroup(path=path, memory_current=mb * MB, frozen_since=frozen_since)


def snap(apps, pressure=Pressure.HIGH, focus=None, now=NOW, focus_known=True) -> Snapshot:
    return Snapshot(
        apps=tuple(apps), focus_path=focus, focus_known=focus_known, pressure=pressure, now=now
    )


# --- dondurma: aday seçimi -------------------------------------------------

def test_freezes_largest_unfocused_app_under_high_pressure():
    s = snap([app(CALC, 300), app(FIREFOX, 900), app(TERMINAL, 80)], focus=CALC)
    assert decide(s, POLICY) == (Freeze(FIREFOX),)


def test_never_freezes_focused_app_even_when_it_is_largest():
    s = snap([app(CALC, 1500), app(FIREFOX, 400)], focus=CALC)
    assert decide(s, POLICY) == (Freeze(FIREFOX),)


def test_focus_on_a_child_cgroup_protects_the_app_scope():
    s = snap([app(FIREFOX, 900), app(CALC, 300)], focus=f"{FIREFOX}/renderer")
    assert decide(s, POLICY) == (Freeze(CALC),)


def test_never_freezes_protected_app_even_when_it_is_largest():
    s = snap([app(PANEL, 2000), app(FIREFOX, 400)])
    assert decide(s, POLICY) == (Freeze(FIREFOX),)


def test_never_freezes_cgroups_outside_app_slice():
    s = snap([app(XFCE_SESSION, 3000), app(PIPEWIRE, 2500), app(TERMINAL, 100)])
    assert decide(s, POLICY) == (Freeze(TERMINAL),)


def test_rejects_lookalike_path_that_only_contains_app_slice_text():
    fake = "/user.slice/user-1000.slice/session-2.scope/app.slice/evil.scope"
    s = snap([app(fake, 3000)])
    assert decide(s, POLICY) == ()


@pytest.mark.parametrize(
    "path",
    [
        f"{APP_SLICE}/../session.slice/x.scope",  # dizin geçişi app.slice'tan kaçar
        f"{APP_SLICE}/./x.scope",
        f"{FIREFOX}\n",  # sonda satır sonu
        "/user.slice/user-٣.slice/user@٣.service/app.slice/x.scope",  # ASCII olmayan rakam
        "/user.slice/user-0.slice/user@0.service/app.slice/x.scope",  # başka kullanıcı (root)
        "/user.slice/user-1000.slice/user@1001.service/app.slice/x.scope",  # uid uyuşmuyor
        f"{FIREFOX}/inner.scope",  # scope içinde scope
        f"{APP_SLICE}/dconf.service",  # servis, uygulama scope'u değil
        f"{FIREFOX}/",  # sonda eğik çizgi
    ],
)
def test_rejects_malformed_or_foreign_paths(path):
    assert decide(snap([app(path, 3000)]), POLICY) == ()


def test_accepts_app_scope_inside_nested_slice():
    nested = f"{APP_SLICE}/app-org.gnome.Terminal.slice/vte-spawn-1.scope"
    assert decide(snap([app(nested, 300)]), POLICY) == (Freeze(nested),)


def test_never_freezes_app_inside_protected_slice():
    inside = f"{APP_SLICE}/xfce4-panel.slice/plugin-7.scope"
    s = snap([app(inside, 2000), app(TERMINAL, 100)])
    assert decide(s, POLICY) == (Freeze(TERMINAL),)


def test_does_not_freeze_anything_when_focus_is_unknown():
    s = snap([app(FIREFOX, 900), app(CALC, 300)], focus=None, focus_known=False)
    assert decide(s, POLICY) == ()


def test_unknown_focus_still_allows_timeout_thaw():
    s = snap([app(FIREFOX, 5, frozen_since=NOW - 700)], focus=None, focus_known=False)
    assert decide(s, POLICY) == (Thaw(FIREFOX, "timeout"),)


def test_focus_does_not_match_sibling_scope_with_longer_name():
    short = f"{APP_SLICE}/app-nefes-firefox-1.scope"
    s = snap([app(short, 900)], focus=f"{APP_SLICE}/app-nefes-firefox-11.scope")
    assert decide(s, POLICY) == (Freeze(short),)


def test_duplicate_snapshot_entries_produce_one_action_per_path():
    s = snap([app(FIREFOX, 5, frozen_since=NOW - 700), app(FIREFOX, 5, frozen_since=NOW - 700)],
             pressure=Pressure.NORMAL)
    assert decide(s, POLICY) == (Thaw(FIREFOX, "timeout"),)


def test_skips_already_frozen_app_and_freezes_next_largest():
    s = snap([app(FIREFOX, 900, frozen_since=NOW - 5), app(TERMINAL, 200)])
    assert decide(s, POLICY) == (Freeze(TERMINAL),)


def test_ignores_apps_smaller_than_minimum_candidate_size():
    s = snap([app(TERMINAL, 49)])
    assert decide(s, POLICY) == ()


def test_app_exactly_at_minimum_size_is_a_candidate():
    s = snap([app(TERMINAL, 50)])
    assert decide(s, POLICY) == (Freeze(TERMINAL),)


def test_does_nothing_under_high_pressure_when_only_focused_app_remains():
    s = snap([app(CALC, 1500)], focus=CALC)
    assert decide(s, POLICY) == ()


def test_does_not_freeze_without_high_pressure():
    s = snap([app(FIREFOX, 900)], pressure=Pressure.NORMAL)
    assert decide(s, POLICY) == ()


# --- çözme -----------------------------------------------------------------

def test_thaws_app_frozen_longer_than_max_duration():
    s = snap([app(FIREFOX, 5, frozen_since=NOW - 601)], pressure=Pressure.NORMAL)
    assert decide(s, POLICY) == (Thaw(FIREFOX, "timeout"),)


def test_keeps_app_frozen_at_exactly_max_duration():
    s = snap([app(FIREFOX, 5, frozen_since=NOW - 600)], pressure=Pressure.NORMAL)
    assert decide(s, POLICY) == ()


def test_focus_reason_wins_when_app_is_also_timed_out():
    s = snap([app(FIREFOX, 5, frozen_since=NOW - 700)], pressure=Pressure.NORMAL, focus=FIREFOX)
    assert decide(s, POLICY) == (Thaw(FIREFOX, "focus"),)


def test_safe_pressure_does_not_thaw_the_same_app_twice():
    s = snap(
        [app(FIREFOX, 5, frozen_since=NOW - 700), app(CALC, 5, frozen_since=NOW - 90)],
        pressure=Pressure.SAFE,
    )
    assert decide(s, POLICY) == (Thaw(FIREFOX, "timeout"), Thaw(CALC, "pressure_low"))


def test_keeps_app_frozen_just_below_max_duration():
    s = snap([app(FIREFOX, 5, frozen_since=NOW - 599)], pressure=Pressure.NORMAL)
    assert decide(s, POLICY) == ()


def test_timeout_thaw_happens_even_under_high_pressure():
    s = snap([app(FIREFOX, 5, frozen_since=NOW - 700), app(CALC, 300)])
    assert decide(s, POLICY) == (Thaw(FIREFOX, "timeout"), Freeze(CALC))


def test_thaws_frozen_app_immediately_when_it_gains_focus():
    s = snap([app(FIREFOX, 5, frozen_since=NOW - 10)], pressure=Pressure.HIGH, focus=FIREFOX)
    assert decide(s, POLICY) == (Thaw(FIREFOX, "focus"),)


def test_thaws_only_the_longest_frozen_app_when_pressure_is_safe():
    s = snap(
        [app(FIREFOX, 5, frozen_since=NOW - 30), app(CALC, 5, frozen_since=NOW - 90)],
        pressure=Pressure.SAFE,
    )
    assert decide(s, POLICY) == (Thaw(CALC, "pressure_low"),)


def test_safe_pressure_does_not_thaw_an_app_frozen_for_less_than_the_minimum():
    # Gerçek sistemde bulunan hata (2026-11-23): tetik kısa süreli bekleme ile gelir ama avg10
    # o anda zaten "güvenli" olabilir → uygulama 2 s sonra çözülüp gidip geliyordu.
    s = snap([app(FIREFOX, 5, frozen_since=NOW - 10)], pressure=Pressure.SAFE)
    assert decide(s, POLICY) == ()


def test_safe_pressure_thaws_an_app_frozen_exactly_the_minimum():
    s = snap([app(FIREFOX, 5, frozen_since=NOW - 30)], pressure=Pressure.SAFE)
    assert decide(s, POLICY) == (Thaw(FIREFOX, "pressure_low"),)


def test_minimum_frozen_time_does_not_delay_a_focus_thaw():
    s = snap([app(FIREFOX, 5, frozen_since=NOW - 1)], pressure=Pressure.SAFE, focus=FIREFOX)
    assert decide(s, POLICY) == (Thaw(FIREFOX, "focus"),)


def test_safe_pressure_without_frozen_apps_does_nothing():
    s = snap([app(FIREFOX, 900)], pressure=Pressure.SAFE)
    assert decide(s, POLICY) == ()
