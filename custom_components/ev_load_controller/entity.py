from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .controller import Controller


class ControllerEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, controller: Controller, key: str) -> None:
        self.controller = controller
        self._attr_translation_key = key
        self._attr_unique_id = f"{controller.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, controller.entry.entry_id)},
            name=controller.entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )


class SettingEntity(ControllerEntity):
    """Writes its value into controller.settings and re-runs the decision."""

    def _apply(self, value) -> None:
        setattr(self.controller.settings, self.entity_description.key, value)
        if self.controller.decision is not None:
            self.controller.async_update()
