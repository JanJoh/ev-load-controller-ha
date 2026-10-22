from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .const import CONF_CHARGER, CONF_CONNECTOR_STATUS, CONF_DLM, CONF_GRID, CONF_PRICE, DOMAIN

PHASE_GROUPS = (CONF_DLM, CONF_GRID, CONF_CHARGER)
_SENSOR = EntitySelector(EntitySelectorConfig(domain="sensor"))


def _schema(current: dict[str, Any]) -> vol.Schema:
    """One field per phase in the form; stored as a three-item list per group."""
    fields: dict = {}
    for group in PHASE_GROUPS:
        for i, entity_id in enumerate(current.get(group) or [None] * 3):
            key = f"{group}_l{i + 1}"
            fields[vol.Required(key, default=entity_id) if entity_id else vol.Required(key)] = _SENSOR
    status = current.get(CONF_CONNECTOR_STATUS)
    fields[vol.Required(CONF_CONNECTOR_STATUS, default=status) if status else vol.Required(CONF_CONNECTOR_STATUS)] = _SENSOR
    price = current.get(CONF_PRICE)
    fields[vol.Optional(CONF_PRICE, description={"suggested_value": price})] = _SENSOR
    return vol.Schema(fields)


def _collect(user_input: dict[str, Any]) -> dict[str, Any]:
    data = {group: [user_input[f"{group}_l{i}"] for i in (1, 2, 3)] for group in PHASE_GROUPS}
    data[CONF_CONNECTOR_STATUS] = user_input[CONF_CONNECTOR_STATUS]
    if user_input.get(CONF_PRICE):
        data[CONF_PRICE] = user_input[CONF_PRICE]
    return data


class EvLoadControllerConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="EV load controller", data=_collect(user_input))
        return self.async_show_form(step_id="user", data_schema=_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EvLoadControllerOptionsFlow()


class EvLoadControllerOptionsFlow(OptionsFlow):

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=_collect(user_input))
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_schema(current))
