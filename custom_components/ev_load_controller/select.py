from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import EvLoadControllerConfigEntry
from .core import ACCESS_MODES, FALLBACK_MODES, PRICE_MODES
from .entity import SettingEntity


@dataclass(frozen=True, kw_only=True)
class SettingSelectDescription(SelectEntityDescription):
    pass


SELECTS = (
    # Settings field names: fallback, price_mode, access.
    SettingSelectDescription(key="fallback", options=list(FALLBACK_MODES), entity_category=EntityCategory.CONFIG),
    SettingSelectDescription(key="price_mode", options=list(PRICE_MODES)),
    SettingSelectDescription(key="access", options=list(ACCESS_MODES)),
)


async def async_setup_entry(hass: HomeAssistant, entry: EvLoadControllerConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(SettingSelect(entry.runtime_data, d) for d in SELECTS)


class SettingSelect(SettingEntity, SelectEntity, RestoreEntity):
    entity_description: SettingSelectDescription

    def __init__(self, controller, description: SettingSelectDescription) -> None:
        super().__init__(controller, description.key)
        self.entity_description = description
        self._attr_current_option = getattr(controller.settings, description.key)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in self.options:
            self._attr_current_option = last.state
        self._apply(self._attr_current_option)

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        self._apply(option)
        self.async_write_ha_state()
