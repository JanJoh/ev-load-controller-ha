DOMAIN = "ev_load_controller"
PLATFORMS: list[str] = ["number", "select", "sensor"]

CONF_DLM = "dlm_limits"
CONF_GRID = "grid_currents"
CONF_CHARGER = "charger_currents"
CONF_CONNECTOR_STATUS = "connector_status"
CONF_PRICE = "price"

UPDATE_INTERVAL_SECONDS = 10

# Fired whenever the decided limit or availability changes.
EVENT_DECISION = f"{DOMAIN}_decision"

# Sensors may carry the time their value was measured, which can be older than
# the last state write (the GARO balancer integration sets this for DLM limits).
MEASURED_AT_ATTRIBUTES = ("logged_at", "data_captured_at")
