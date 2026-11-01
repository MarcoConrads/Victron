#!/usr/bin/env python3
"""Standalone Peblar EV charger service using the shared Modbus/DBus base."""

import logging
import math
import sys
import time

import dbus.mainloop.glib
from gi.repository import GLib
from pymodbus.client.sync import ModbusTcpClient

sys.path.insert(0, "/opt/victronenergy/dbus-systemcalc-py/ext/velib_python")
sys.path.insert(0, "/data/velib_python")

from base_modbus_dbus import BaseModbusDbus
from modbus_types import MODBUS_TYPES
from peblar_dbus_config import (
    DEVICE_INSTANCE, HOST, MIN_CURRENT_A, POLL_INTERVAL_MS, PORT,
    REG_CHARGE_CURRENT_LIMIT, UNIT_ID,
)
from peblar_dbus_registers import REG


class DbusPeblar(BaseModbusDbus):
    regs = REG
    host = HOST
    port = PORT
    unit_id = UNIT_ID
    service_name = f"com.victronenergy.evcharger.peblar_{DEVICE_INSTANCE}"

    def __init__(self):
        self._session_start = None
        self._last_nonzero_a = float(MIN_CURRENT_A)
        super().__init__()

    @classmethod
    def build_modbus_messages(cls, regs):
        """Read contiguous known registers only; skip undocumented address gaps."""
        messages = []
        for regtype in MODBUS_TYPES:
            addresses = sorted({
                address
                for reg in regs if reg["regtype"] == regtype and reg["address"] is not None
                for address in range(reg["address"], reg["address"] + reg["length"])
            })
            for address in addresses:
                if (messages and messages[-1]["regtype"] == regtype
                        and messages[-1]["start"] + messages[-1]["count"] == address
                        and messages[-1]["count"] < cls.max_items_for_regtype(regtype)):
                    messages[-1]["count"] += 1
                else:
                    messages.append({"regtype": regtype, "start": address, "count": 1})
        return messages

    def add_extra_paths(self):
        self.service.add_path("/SetCurrent", 0.0, writeable=True,
                              onchangecallback=self.set_current)
        self.service.add_path("/StartStop", 0, writeable=True,
                              onchangecallback=self.set_start_stop)
        self.service.add_path("/Session/Time", 0)

    def set_setting_value(self, path, value):
        reg = next((reg for reg in self.regs
                    if reg.get("writeable") and path in self.get_paths(reg)), None)
        if reg is None:
            return False
        if "cast" in reg:
            try:
                number = float(value)
                if not math.isfinite(number) or not number.is_integer():
                    return False
                if not reg["setting_min"] <= number <= reg["setting_max"]:
                    return False
                value = int(number)
            except (TypeError, ValueError, OverflowError):
                return False
        return super().set_setting_value(path, value)

    def after_modbus_update(self, decoded):
        current_limit = decoded.get("charge_current_limit")
        if current_limit is not None:
            if current_limit > 0:
                self._last_nonzero_a = current_limit
            self.service["/SetCurrent"] = current_limit
            self.service["/StartStop"] = int(current_limit > 0)

        now = time.monotonic()
        if decoded.get("l1_current", 0.0) > 0.1:
            if self._session_start is None:
                self._session_start = now
            self.service["/Session/Time"] = int(now - self._session_start)
        else:
            self._session_start = None
            self.service["/Session/Time"] = 0

    def apply_read_error_policy(self):
        super().apply_read_error_policy()
        # A lost connection cannot provide a reliable continuous session time.
        self._session_start = None
        self.service["/Session/Time"] = 0

    def _write_current(self, amps):
        milliamps = int(round(amps * 1000.0))
        client = ModbusTcpClient(self.host, port=self.port, timeout=3)
        try:
            if not client.connect():
                logging.error("Unable to connect to Peblar charger")
                return False
            response = client.write_registers(
                REG_CHARGE_CURRENT_LIMIT,
                [(milliamps >> 16) & 0xFFFF, milliamps & 0xFFFF],
                unit=self.unit_id,
            )
            if response.isError():
                logging.error("Failed to write charge current: %s", response)
                return False
        except Exception:
            logging.exception("Peblar current update failed")
            return False
        finally:
            client.close()

        actual_amps = milliamps / 1000.0
        if actual_amps > 0:
            self._last_nonzero_a = actual_amps
        self.service["/SetCurrent"] = actual_amps
        self.service["/StartStop"] = int(milliamps > 0)
        return True

    def set_current(self, path, value):
        try:
            amps = float(value)
            if not math.isfinite(amps):
                return False
            if amps != 0 and not MIN_CURRENT_A <= amps <= self.settings["maxcurrent"]:
                return False
        except (TypeError, ValueError, OverflowError):
            return False
        return self._write_current(amps)

    def set_start_stop(self, path, value):
        try:
            command = float(value)
        except (TypeError, ValueError, OverflowError):
            return False
        if command == 0:
            return self._write_current(0.0)
        if command == 1:
            amps = min(max(MIN_CURRENT_A, self._last_nonzero_a), self.settings["maxcurrent"])
            return self._write_current(amps)
        return False


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    charger = DbusPeblar()
    GLib.timeout_add(POLL_INTERVAL_MS, charger.poll)
    charger.poll()
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
