"""Feeds Home Assistant states into core.decide() and publishes the result.

Shadow mode only: the decision is exposed as entities, logged and fired as an
event, but nothing is sent to the charger yet.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CHARGER, CONF_CONNECTOR_STATUS, CONF_DLM, CONF_GRID, CONF_PRICE,
    EVENT_DECISION, MEASURED_AT_ATTRIBUTES, UPDATE_INTERVAL_SECONDS,
)
from .core import ControllerState, Decision, Inputs, Settings, decide

_LOGGER = logging.getLogger(__name__)


def _number(state: State | None) -> float | None:
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    try:
        return float(state.state)
    except ValueError:
        return None


def _measured_at(state: State | None) -> datetime | None:
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    for attr in MEASURED_AT_ATTRIBUTES:
        value = state.attributes.get(attr)
        if value:
            parsed = dt_util.parse_datetime(str(value))
            if parsed is not None:
                return parsed
    return state.last_reported


def _oldest(states: list[State | None]) -> datetime | None:
    times = [_measured_at(s) for s in states]
    return None if None in times else min(times)


class Controller:

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.settings = Settings()
        self.state = ControllerState()
        self.decision: Decision | None = None
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[CALLBACK_TYPE] = []

    def _config(self, key):
        return self.entry.options.get(key, self.entry.data.get(key))

    @property
    def input_entities(self) -> list[str]:
        ids = [*self._config(CONF_DLM), *self._config(CONF_GRID), *self._config(CONF_CHARGER),
               self._config(CONF_CONNECTOR_STATUS)]
        if self._config(CONF_PRICE):
            ids.append(self._config(CONF_PRICE))
        return ids

    def async_start(self) -> None:
        self._unsubs.append(async_track_state_change_event(self.hass, self.input_entities, self._on_state_change))
        self._unsubs.append(async_track_time_interval(
            self.hass, self._on_interval, timedelta(seconds=UPDATE_INTERVAL_SECONDS)))
        self.async_update()

    def async_stop(self) -> None:
        while self._unsubs:
            self._unsubs.pop()()

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def _on_state_change(self, event: Event) -> None:
        self.async_update()

    @callback
    def _on_interval(self, now: datetime) -> None:
        self.async_update()

    def read_inputs(self) -> Inputs:
        get = self.hass.states.get
        dlm = [get(e) for e in self._config(CONF_DLM)]
        grid = [get(e) for e in self._config(CONF_GRID)]
        charger = [get(e) for e in self._config(CONF_CHARGER)]
        status = get(self._config(CONF_CONNECTOR_STATUS))
        price_entity = self._config(CONF_PRICE)
        return Inputs(
            now=dt_util.utcnow(),
            connector_status=status.state if status else None,
            dlm=tuple(_number(s) for s in dlm),
            dlm_updated=_oldest(dlm),
            grid=tuple(_number(s) for s in grid),
            grid_updated=_oldest(grid),
            charger=tuple(_number(s) for s in charger),
            price=_number(get(price_entity)) if price_entity else None,
        )

    @callback
    def async_update(self) -> None:
        previous = self.decision
        self.decision = decide(self.read_inputs(), self.settings, self.state)
        d = self.decision
        if previous is None or (d.limit, d.availability) != (previous.limit, previous.availability):
            _LOGGER.info("Would set %s A, availability %s (%s; phases %s)",
                         d.limit, d.availability, d.reason, ",".join(d.phases) or "unknown")
            self.hass.bus.async_fire(EVENT_DECISION, {
                "limit": d.limit,
                "previous_limit": previous.limit if previous else None,
                "availability": d.availability,
                "reason": d.reason,
                "phases": list(d.phases),
            })
        for listener in list(self._listeners):
            listener()
