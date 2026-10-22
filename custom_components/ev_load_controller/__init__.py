from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .controller import Controller

type EvLoadControllerConfigEntry = ConfigEntry[Controller]


async def async_setup_entry(hass: HomeAssistant, entry: EvLoadControllerConfigEntry) -> bool:
    controller = Controller(hass, entry)
    entry.runtime_data = controller
    # Settings entities restore their values while the platforms load, so the
    # controller starts only after they are in place.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    controller.async_start()
    entry.async_on_unload(controller.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: EvLoadControllerConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: EvLoadControllerConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
