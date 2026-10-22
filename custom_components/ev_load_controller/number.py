from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntityDescription, NumberMode, RestoreNumber
from homeassistant.const import EntityCategory, UnitOfElectricCurrent, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EvLoadControllerConfigEntry
from .core import Settings
from .entity import SettingEntity

_DEFAULTS = Settings()


@dataclass(frozen=True, kw_only=True)
class SettingNumberDescription(NumberEntityDescription):
    default: float


NUMBERS = (
    SettingNumberDescription(key="main_fuse", native_min_value=10, native_max_value=63, native_step=1,
                             native_unit_of_measurement=UnitOfElectricCurrent.AMPERE, default=_DEFAULTS.main_fuse),
    SettingNumberDescription(key="margin", native_min_value=0, native_max_value=10, native_step=0.5,
                             native_unit_of_measurement=UnitOfElectricCurrent.AMPERE, default=_DEFAULTS.margin),
    SettingNumberDescription(key="max_current", native_min_value=6, native_max_value=32, native_step=1,
                             native_unit_of_measurement=UnitOfElectricCurrent.AMPERE, default=_DEFAULTS.max_current),
    SettingNumberDescription(key="data_timeout", native_min_value=20, native_max_value=600, native_step=5,
                             native_unit_of_measurement=UnitOfTime.SECONDS, default=_DEFAULTS.data_timeout),
    SettingNumberDescription(key="raise_delay", native_min_value=0, native_max_value=600, native_step=5,
                             native_unit_of_measurement=UnitOfTime.SECONDS, default=_DEFAULTS.raise_delay),
    SettingNumberDescription(key="price_cap", native_min_value=0, native_max_value=10, native_step=0.05,
                             default=_DEFAULTS.price_cap),
)


async def async_setup_entry(hass: HomeAssistant, entry: EvLoadControllerConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(SettingNumber(entry.runtime_data, d) for d in NUMBERS)


class SettingNumber(SettingEntity, RestoreNumber):
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG
    entity_description: SettingNumberDescription

    def __init__(self, controller, description: SettingNumberDescription) -> None:
        super().__init__(controller, description.key)
        self.entity_description = description
        self._attr_native_value = description.default

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = last.native_value
        self._apply(self._attr_native_value)

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self._apply(value)
        self.async_write_ha_state()
