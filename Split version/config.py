# Configuration for the Growatt DBus Modbus service.

HOST = "192.168.11.68"
PORT = 502
UNIT_ID = 2

DEVICE_INSTANCE = 48
POLL_INTERVAL_MS = 1000

DEFAULT_MAX_POWER_W = 10000

# Holding register for total active power limit.
# The register expects a value from 0 to 100 percent.
REG_POWER_LIMIT_TOTAL = 3
