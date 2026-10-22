# EV Load Controller

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)

Home Assistant integration that decides how much current an EV charger may offer, based on per-phase headroom from a load balancer, which phases the car actually uses, a fallback for stale data, a price gate and an access policy.

> **Status: 0.1, shadow mode.** The integration calculates and publishes the limit it *would* set, but sends nothing to the charger yet. Sending through the [OCPP integration](https://github.com/lbbrhzn/ocpp) comes in a later version.

> Mostly LLM-generated code. It works, but don't expect miracles.

---

## Why

A load balancer such as the GARO Entity Balance limits a charger to the tightest of the three phases. A car that charges on one phase (most plug-in hybrids) is then held back by a phase it does not use. This controller learns which phases the car draws on during the session and only counts those.

## How it decides

1. **Headroom per phase:** the load balancer's DLM limits, as long as they are fresher than *Data timeout*.
2. **Active phases:** any phase where the charger draws more than 1 A joins and stays until the car is unplugged (connector status `Available`). Until the car draws current, all three phases count.
3. **Limit:** the lowest headroom among the active phases, capped by *Max charging current*.
4. **Fallback** when the DLM data is stale or missing:
   - *Limit to 6 A* (default)
   - *Pause* (0 A)
   - *Own calculation*: main fuse − safety margin − (grid current − charger current), per phase
5. **Price mode:** *Charge now*, *Price cap* (0 A while the price sensor is above the cap) or *Off*.
6. **Charger access:** *Open*, *Locked for new sessions* (a running session continues) or *Locked*.
7. **Below 6 A** the car cannot charge, so the limit becomes 0 A.
8. **Lowering takes effect at once; raising waits** until the previous change is at least *Raise delay* old.

## Entities

| Entity | Purpose |
|---|---|
| `sensor.…_current_limit` | The limit it would set (attributes: target, raise pending, source, limiting phase) |
| `sensor.…_reason` | Why |
| `sensor.…_active_phases` | Phases learned this session |
| `sensor.…_availability` | OCPP availability it would set |
| `select.…_fallback_mode`, `…_price_mode`, `…_charger_access` | Modes |
| `number.…_main_fuse`, `…_safety_margin`, `…_max_charging_current`, `…_data_timeout`, `…_raise_delay`, `…_price_cap` | Settings |

Every change of limit or availability fires the event `ev_load_controller_decision`.

## Inputs

Picked in the setup dialog, one sensor per phase where it applies:

| Input | Example (GARO) |
|---|---|
| Load balancer DLM limit L1–L3 | [GARO Entity Balance Meter](https://github.com/JanJoh/Garo-entity-balance-meter-ha) `dlm_limit_l1…l3` |
| Grid current L1–L3 | GARO Entity Balance Meter `current_l1…l3` |
| Charger current L1–L3 | [GARO Entity Charger Meter](https://github.com/JanJoh/Garo-entity-charger-meter-ha) `l1…l3_current` |
| Charger connector status | GARO Entity Charger Meter `connector_status` |
| Electricity price (optional) | e.g. Nord Pool, or a template sensor with fees included |

Freshness is read from a sensor's `logged_at` attribute when it has one (the GARO balancer integration sets it to the time of the log line), otherwise from the time the state was last reported.

## Installation

### HACS

1. HACS → **Custom repositories** → add `https://github.com/JanJoh/ev-load-controller-ha` as type **Integration**
2. Install **EV Load Controller** and restart Home Assistant
3. Settings → Devices & Services → **Add integration** → *EV Load Controller*

### Manual

Copy `custom_components/ev_load_controller/` into `config/custom_components/` and restart.

## Development

```
pip install -r requirements_test.txt
pytest
```

`core.py` holds the decision logic without any Home Assistant dependency; most behaviour is tested there.
