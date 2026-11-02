#!/usr/bin/env python3
# /data/dbus-growatt/dbus_growatt.py

import logging
import sys

from gi.repository import GLib
import dbus.mainloop.glib

sys.path.insert(0, "/opt/victronenergy/dbus-systemcalc-py/ext/velib_python")
sys.path.insert(0, "/data/velib_python")

from growatt_dbus_config import (
    DEFAULT_MAX_POWER_W,
    POLL_INTERVAL_MS,
    DEVICE_INSTANCE,
    HOST,
    PORT,
    REG_POWER_LIMIT_TOTAL,
    UNIT_ID,
)

import logging
from pymodbus.client.sync import ModbusTcpClient
from base_modbus_dbus import BaseModbusDbus
from growatt_dbus_registers import REG

class DbusGrowatt(BaseModbusDbus):
    regs = REG
    host = HOST
    port = PORT
    unit_id = UNIT_ID
    service_name = f"com.victronenergy.pvinverter.growatt_{DEVICE_INSTANCE}"

    def __init__(self):
        self.max_power_w = DEFAULT_MAX_POWER_W
        super().__init__()

    def add_extra_paths(self):
        self.service.add_path("/Ac/L1/Energy/Forward", 0.0)
        self.service.add_path("/Ac/L2/Energy/Forward", 0.0)
        self.service.add_path("/Ac/L3/Energy/Forward", 0.0)

        self.service.add_path(
            "/Ac/PowerLimit",
            0.0,
            writeable=True,
            onchangecallback=self.set_power_limit,
        )

    def after_modbus_update(self, decoded):
        if decoded.get("maxpower"):
            self.max_power_w = float(decoded["maxpower"])

        self.write_derived_values(decoded)

    def write_derived_values(self, decoded):
        """Write DBus values that are derived from multiple registers."""
        total_energy = decoded.get("total_energy")
        if total_energy is not None:
            phase_energy = total_energy / 3.0
            self.service["/Ac/L1/Energy/Forward"] = phase_energy
            self.service["/Ac/L2/Energy/Forward"] = phase_energy
            self.service["/Ac/L3/Energy/Forward"] = phase_energy

        power_limit_percent = decoded.get("power_limit_percent")
        if power_limit_percent is not None:
            power_limit_percent = max(0.0, min(100.0, float(power_limit_percent)))
            self.service["/Ac/PowerLimit"] = power_limit_percent * self.get_power_limit_scale()

    def get_power_limit_scale(self):
        """Return watts per percent point for the 0-100% limit register."""
        max_power_w = float(self.max_power_w or DEFAULT_MAX_POWER_W)

        if max_power_w <= 0:
            max_power_w = DEFAULT_MAX_POWER_W

        return max_power_w / 100.0

    def set_power_limit(self, path, value):
        try:
            watts = int(float(value))

            if watts < 0:
                watts = 0

            max_power_w = int(float(self.max_power_w or DEFAULT_MAX_POWER_W))
            if max_power_w <= 0:
                max_power_w = DEFAULT_MAX_POWER_W

            if watts > max_power_w:
                watts = max_power_w

            power_limit_scale = self.get_power_limit_scale()
            register_value = int(round(watts / power_limit_scale))
            register_value = max(0, min(100, register_value))

            client = ModbusTcpClient(self.host, port=self.port, timeout=3)

            try:
                if not client.connect():
                    logging.error("Unable to connect to inverter")
                    return False

                rr = client.write_register(
                    REG_POWER_LIMIT_TOTAL,
                    register_value,
                    unit=self.unit_id,
                )
            finally:
                client.close()

            if rr.isError():
                logging.error("Failed to write power limit: %s", rr)
                return False

            self.service["/Ac/PowerLimit"] = watts
            logging.info(
                "3-phase power limit set to %s W (%s%% of %s W)",
                watts,
                register_value,
                max_power_w,
            )
            return True

        except Exception as e:
            logging.exception("Power limit update failed: %s", e)
            return False


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )
    inverter = DbusGrowatt()
    GLib.timeout_add(POLL_INTERVAL_MS, inverter.poll)
    inverter.poll()
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
