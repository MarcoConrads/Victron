#!/usr/bin/env python3
# /data/dbus-growatt/dbus_growatt.py

import logging
import sys

from gi.repository import GLib
import dbus.mainloop.glib

sys.path.insert(0, "/opt/victronenergy/dbus-systemcalc-py/ext/velib_python")
sys.path.insert(0, "/data/velib_python")

from growatt_dbus_config import (
    POLL_INTERVAL_MS,
    DEVICE_INSTANCE,
    HOST,
    PORT,
    UNIT_ID,
)

import logging
from pymodbus.client.sync import ModbusTcpClient
from base_modbus_dbus import BaseModbusDbus
from growatt_dbus_registers import REG

class DbusEcoforest(BaseModbusDbus):
    regs = REG
    host = HOST
    port = PORT
    unit_id = UNIT_ID
    service_name = f"com.victronenergy.heatpump.ecoforest_{DEVICE_INSTANCE}"

def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )
    inverter = DbusEcoforest()
    GLib.timeout_add(POLL_INTERVAL_MS, inverter.poll)
    inverter.poll()
    GLib.MainLoop().run()

if __name__ == "__main__":
    main()
