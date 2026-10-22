from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EvLoadControllerConfigEntry
from .core import (
    AVAILABILITY_INOPERATIVE, AVAILABILITY_OPERATIVE, AVAILABILITY_SCHEDULED, AVAILABILITY_STOP, Decision,
)
from .entity import ControllerEntity


@dataclass(frozen=True, kw_only=True)
class DecisionSensorDescription(SensorEntityDescription):
    value: Callable[[Decision], object]
    attributes: Callable[[Decision], dict] = lambda d: {}


SENSORS = (
    DecisionSensorDescription(
        key="current_limit",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value=lambda d: d.limit,
        attributes=lambda d: {
            "target": d.target,
            "raise_pending": d.raise_pending,
            "source": d.source,
            "limiting_phase": d.limiting_phase,
        },
    ),
    DecisionSensorDescription(key="reason", value=lambda d: d.reason),
    DecisionSensorDescription(key="active_phases", value=lambda d: ",".join(d.phases) or "unknown"),
    DecisionSensorDescription(
        key="availability",
        device_class=SensorDeviceClass.ENUM,
        options=[AVAILABILITY_OPERATIVE, AVAILABILITY_SCHEDULED, AVAILABILITY_INOPERATIVE, AVAILABILITY_STOP],
        value=lambda d: d.availability,
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: EvLoadControllerConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(DecisionSensor(entry.runtime_data, d) for d in SENSORS)


class DecisionSensor(ControllerEntity, SensorEntity):
    entity_description: DecisionSensorDescription

    def __init__(self, controller, description: DecisionSensorDescription) -> None:
        super().__init__(controller, description.key)
        self.entity_description = description

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.controller.async_add_listener(self._on_decision))

    @callback
    def _on_decision(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self.controller.decision is not None

    @property
    def native_value(self):
        d = self.controller.decision
        return None if d is None else self.entity_description.value(d)

    @property
    def extra_state_attributes(self) -> dict | None:
        d = self.controller.decision
        return None if d is None else self.entity_description.attributes(d) or None
