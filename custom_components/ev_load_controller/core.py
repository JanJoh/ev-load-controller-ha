"""Charging decision, free of Home Assistant so it can be unit tested on its own.

decide() turns one snapshot of measurements and settings into the current an
OCPP controller should offer, plus the reason. State that has to survive
between calls (which phases the car uses this session, when the limit last
changed) lives in ControllerState and is updated in place.

Rules, in order:
  * Headroom per phase comes from the load balancer's DLM limits while they
    are fresh; otherwise from the fallback mode.
  * Only the phases the car draws on count. They are learned during the
    session (any phase above PHASE_ACTIVE_A joins and stays until the car is
    unplugged); until then all three count.
  * The price gate and the access policy can force 0 A.
  * Below MIN_CHARGE_A the car cannot charge, so the result is 0 A (pause).
  * Lowering takes effect at once; raising waits until the previous change
    is at least raise_delay seconds old.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

PHASES = ("L1", "L2", "L3")
PHASE_ACTIVE_A = 1.0
MIN_CHARGE_A = 6

FALLBACK_MIN = "min_current"
FALLBACK_PAUSE = "pause"
FALLBACK_OWN = "own_calculation"
FALLBACK_MODES = (FALLBACK_MIN, FALLBACK_PAUSE, FALLBACK_OWN)

PRICE_NOW = "charge_now"
PRICE_CAP = "price_cap"
PRICE_OFF = "off"
PRICE_MODES = (PRICE_NOW, PRICE_CAP, PRICE_OFF)

ACCESS_OPEN = "open"
ACCESS_LOCKED_NEW = "locked_for_new"
ACCESS_LOCKED = "locked"
ACCESS_MODES = (ACCESS_OPEN, ACCESS_LOCKED_NEW, ACCESS_LOCKED)

AVAILABILITY_OPERATIVE = "operative"
AVAILABILITY_SCHEDULED = "inoperative_scheduled"
AVAILABILITY_INOPERATIVE = "inoperative"
AVAILABILITY_STOP = "inoperative_stop"

# OCPP 1.6 connector status meaning nothing is plugged in.
DISCONNECTED_STATUSES = ("available",)


@dataclass
class Settings:
    main_fuse: float = 20
    margin: float = 4
    max_current: float = 16
    data_timeout: float = 60
    raise_delay: float = 60
    fallback: str = FALLBACK_MIN
    price_mode: str = PRICE_NOW
    price_cap: float = 1.0
    access: str = ACCESS_OPEN


@dataclass
class Inputs:
    now: datetime
    connector_status: str | None
    dlm: tuple[float | None, float | None, float | None]
    dlm_updated: datetime | None
    grid: tuple[float | None, float | None, float | None]
    grid_updated: datetime | None
    charger: tuple[float | None, float | None, float | None]
    price: float | None = None


@dataclass
class ControllerState:
    phases: set[str] = field(default_factory=set)
    limit: int | None = None
    changed_at: datetime | None = None


@dataclass
class Decision:
    limit: int
    target: int
    reason: str
    source: str
    phases: tuple[str, ...]
    limiting_phase: str | None
    availability: str
    raise_pending: bool


def _fresh(updated: datetime | None, now: datetime, timeout: float) -> bool:
    return updated is not None and (now - updated).total_seconds() <= timeout


def _complete(values) -> bool:
    return all(v is not None for v in values)


def decide(inputs: Inputs, settings: Settings, state: ControllerState) -> Decision:
    status = (inputs.connector_status or "").lower()
    connected = status not in DISCONNECTED_STATUSES and status not in ("", "unknown", "unavailable")

    if status in DISCONNECTED_STATUSES:
        state.phases.clear()
    elif connected:
        for name, amps in zip(PHASES, inputs.charger):
            if amps is not None and amps > PHASE_ACTIVE_A:
                state.phases.add(name)
    counted = [i for i, name in enumerate(PHASES) if name in state.phases] or [0, 1, 2]

    dlm_ok = _complete(inputs.dlm) and _fresh(inputs.dlm_updated, inputs.now, settings.data_timeout)
    own_ok = (_complete(inputs.grid) and _complete(inputs.charger)
              and _fresh(inputs.grid_updated, inputs.now, settings.data_timeout))

    if dlm_ok:
        headroom = [inputs.dlm[i] for i in range(3)]
        source = "dlm"
    elif settings.fallback == FALLBACK_OWN and own_ok:
        headroom = [settings.main_fuse - settings.margin - (inputs.grid[i] - inputs.charger[i]) for i in range(3)]
        source = "own_calculation"
    else:
        headroom = None
        source = "fallback_pause" if settings.fallback == FALLBACK_PAUSE else "fallback_min"

    limiting_phase = None
    if headroom is not None:
        i = min(counted, key=lambda i: headroom[i])
        limiting_phase = PHASES[i]
        balanced = math.floor(headroom[i])
    elif source == "fallback_pause":
        balanced = 0
    else:
        balanced = MIN_CHARGE_A

    price_ok = settings.price_mode == PRICE_NOW or (
        settings.price_mode == PRICE_CAP and inputs.price is not None and inputs.price <= settings.price_cap
    )

    if settings.access == ACCESS_LOCKED:
        target, reason = 0, "charger locked"
    elif not price_ok:
        target, reason = 0, f"price mode {settings.price_mode}" + (
            f" ({inputs.price:.2f})" if inputs.price is not None else " (no price)")
    else:
        target = min(balanced, math.floor(settings.max_current))
        reason = {
            "dlm": f"DLM, tightest {limiting_phase}",
            "own_calculation": f"no DLM data, own calculation, tightest {limiting_phase}",
            "fallback_pause": "no data, fallback: pause",
            "fallback_min": f"no data, fallback: {MIN_CHARGE_A} A",
        }[source]
        if target == math.floor(settings.max_current) and balanced > target:
            reason += ", capped by max current"
    if target < MIN_CHARGE_A:
        target = 0

    raise_pending = False
    limit = target
    if state.limit is not None and target > state.limit and state.changed_at is not None:
        if (inputs.now - state.changed_at).total_seconds() < settings.raise_delay:
            limit, raise_pending = state.limit, True
    if limit != state.limit:
        state.limit, state.changed_at = limit, inputs.now

    if settings.access == ACCESS_LOCKED:
        availability = AVAILABILITY_STOP
    elif settings.access == ACCESS_LOCKED_NEW:
        availability = AVAILABILITY_SCHEDULED if connected else AVAILABILITY_INOPERATIVE
    else:
        availability = AVAILABILITY_OPERATIVE

    return Decision(
        limit=limit,
        target=target,
        reason=reason,
        source=source,
        phases=tuple(p for p in PHASES if p in state.phases),
        limiting_phase=limiting_phase,
        availability=availability,
        raise_pending=raise_pending,
    )
