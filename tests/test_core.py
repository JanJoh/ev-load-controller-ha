from datetime import datetime, timedelta, timezone

from custom_components.ev_load_controller.core import (
    ACCESS_LOCKED, ACCESS_LOCKED_NEW, AVAILABILITY_INOPERATIVE, AVAILABILITY_OPERATIVE, AVAILABILITY_SCHEDULED,
    AVAILABILITY_STOP, FALLBACK_OWN, FALLBACK_PAUSE, PRICE_CAP, PRICE_OFF, ControllerState, Inputs, Settings, decide,
)

T0 = datetime(2026, 10, 22, 17, 0, tzinfo=timezone.utc)


def inputs(t=T0, status="Charging", dlm=(14, 10, 14), dlm_age=5, grid=(13.4, 5.6, 2.5), grid_age=2,
           charger=(10.9, 0.0, 0.0), price=None):
    return Inputs(now=t, connector_status=status, dlm=dlm, dlm_updated=t - timedelta(seconds=dlm_age),
                  grid=grid, grid_updated=t - timedelta(seconds=grid_age), charger=charger, price=price)


def test_single_phase_car_uses_only_its_phase():
    # The situation that started this: the balancer passes 10 A (L2) to a car that only draws on L1.
    d = decide(inputs(), Settings(), ControllerState())
    assert d.limit == 14
    assert d.phases == ("L1",)
    assert d.limiting_phase == "L1"
    assert d.source == "dlm"


def test_unknown_phases_count_all_three():
    d = decide(inputs(status="Preparing", charger=(0.0, 0.0, 0.0)), Settings(), ControllerState())
    assert d.phases == ()
    assert d.limit == 10 and d.limiting_phase == "L2"


def test_phases_latch_until_unplugged():
    s = ControllerState()
    decide(inputs(), Settings(), s)
    # Paused by the car: no current, but L1 stays learned.
    d = decide(inputs(t=T0 + timedelta(seconds=10), status="SuspendedEV", charger=(0, 0, 0)), Settings(), s)
    assert d.phases == ("L1",) and d.limit == 14
    d = decide(inputs(t=T0 + timedelta(seconds=20), status="Available", charger=(0, 0, 0)), Settings(), s)
    assert d.phases == ()


def test_new_phase_joins_and_lowers_at_once():
    s = ControllerState()
    decide(inputs(), Settings(), s)
    d = decide(inputs(t=T0 + timedelta(seconds=5), charger=(10.0, 3.0, 0.0)), Settings(), s)
    assert d.phases == ("L1", "L2")
    assert d.limit == 10 and not d.raise_pending


def test_raise_waits_for_delay():
    s = ControllerState()
    decide(inputs(dlm=(8, 20, 20)), Settings(), s)
    d = decide(inputs(t=T0 + timedelta(seconds=30), dlm=(14, 20, 20)), Settings(), s)
    assert d.limit == 8 and d.target == 14 and d.raise_pending
    d = decide(inputs(t=T0 + timedelta(seconds=61), dlm=(14, 20, 20)), Settings(), s)
    assert d.limit == 14 and not d.raise_pending


def test_max_current_caps():
    d = decide(inputs(dlm=(20, 20, 20)), Settings(max_current=16), ControllerState())
    assert d.limit == 16
    assert "max current" in d.reason


def test_below_minimum_pauses():
    d = decide(inputs(dlm=(5, 20, 20)), Settings(), ControllerState())
    assert d.limit == 0


def test_stale_dlm_falls_back_to_min_current():
    d = decide(inputs(dlm_age=120), Settings(), ControllerState())
    assert d.limit == 6 and d.source == "fallback_min"


def test_missing_dlm_value_falls_back():
    d = decide(inputs(dlm=(14, None, 14)), Settings(), ControllerState())
    assert d.source == "fallback_min"


def test_stale_dlm_pause():
    d = decide(inputs(dlm_age=120), Settings(fallback=FALLBACK_PAUSE), ControllerState())
    assert d.limit == 0 and d.source == "fallback_pause"


def test_own_calculation_subtracts_charger_from_grid():
    # L1: 20 - 4 - (13.4 - 10.9) = 13.5 -> 13
    d = decide(inputs(dlm_age=120), Settings(fallback=FALLBACK_OWN), ControllerState())
    assert d.source == "own_calculation"
    assert d.limit == 13


def test_own_calculation_needs_fresh_grid_data():
    d = decide(inputs(dlm_age=120, grid_age=120), Settings(fallback=FALLBACK_OWN), ControllerState())
    assert d.source == "fallback_min" and d.limit == 6


def test_price_cap():
    assert decide(inputs(price=0.8), Settings(price_mode=PRICE_CAP, price_cap=1.0), ControllerState()).limit == 14
    d = decide(inputs(price=2.6), Settings(price_mode=PRICE_CAP, price_cap=1.0), ControllerState())
    assert d.limit == 0 and "price" in d.reason
    assert decide(inputs(price=None), Settings(price_mode=PRICE_CAP), ControllerState()).limit == 0
    assert decide(inputs(), Settings(price_mode=PRICE_OFF), ControllerState()).limit == 0


def test_access_modes():
    assert decide(inputs(), Settings(), ControllerState()).availability == AVAILABILITY_OPERATIVE
    d = decide(inputs(), Settings(access=ACCESS_LOCKED_NEW), ControllerState())
    assert d.availability == AVAILABILITY_SCHEDULED and d.limit == 14
    d = decide(inputs(status="Available", charger=(0, 0, 0)), Settings(access=ACCESS_LOCKED_NEW), ControllerState())
    assert d.availability == AVAILABILITY_INOPERATIVE
    d = decide(inputs(), Settings(access=ACCESS_LOCKED), ControllerState())
    assert d.availability == AVAILABILITY_STOP and d.limit == 0


def test_unknown_status_keeps_learned_phases():
    s = ControllerState()
    decide(inputs(), Settings(), s)
    d = decide(inputs(t=T0 + timedelta(seconds=10), status="unavailable", charger=(None, None, None)), Settings(), s)
    assert d.phases == ("L1",)
