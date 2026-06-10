#!/usr/bin/env python3
# /data/dbus-growatt/dbus_growatt.py

import sys
import logging
from gi.repository import GLib
import dbus
import dbus.mainloop.glib

sys.path.insert(0, "/opt/victronenergy/dbus-systemcalc-py/ext/velib_python")
sys.path.insert(0, "/data/velib_python")

from vedbus import VeDbusService
from settingsdevice import SettingsDevice
from pymodbus.client.sync import ModbusTcpClient

# ============================================================
# Configuration
# ============================================================

HOST = "192.168.11.68"
PORT = 8002
UNIT_ID = 17

DEVICE_INSTANCE = 48
POLL_INTERVAL_MS = 1000


# Modbus register types
MB_INPUT = "input"
MB_HOLDING = "holding"
MB_NONE = None

# Behaviour on Modbus read error
ON_ERROR_DEFAULT = "default"
ON_ERROR_KEEP = "keep"

MAX_REGISTERS_PER_READ = 125


# ============================================================
# Growatt Modbus Registers
# ============================================================
# Required fields per REG item:
# - path: DBus path or list of DBus paths
# - address: Modbus address
# - length: number of 16-bit Modbus registers
# - regtype: input, holding, or None
# - encoding: s32, u32, ascii
# - default: default DBus value
# - on_error: default writes the default value, keep performs no write action
#
# Extra field scale is used after decoding, because the inverter stores many
# values as fixed-point integers.

REG = [
    # Settings / local DBus-only values
    {
        "name": "custom_name",
        "path": "/CustomName",
        "address": None,
        "length": 0,
        "regtype": MB_NONE,
        "encoding": None,
        "default": "",
        "on_error": ON_ERROR_KEEP,
        "setting": "",
        "setting_path": "/Settings/Devices/Ecoforest/CustomName",
        "writeable": True,
    },
    {
        "name": "position",
        "path": "/Position",
        "address": None,
        "length": 0,
        "regtype": MB_NONE,
        "encoding": None,
        "default": 1,
        "on_error": ON_ERROR_KEEP,
        "setting": 1,
        "setting_path": "/Settings/Devices/Ecoforest/Position",
        "setting_min": 0,
        "setting_max": 2,
        "writeable": True,
        "cast": int,
    },

    # Static product / management information
    {
        "name": "process_name",
        "path": "/Mgmt/ProcessName",
        "address": None,
        "length": 0,
        "regtype": MB_NONE,
        "encoding": "string",
        "default": __file__,
        "on_error": ON_ERROR_KEEP,
    },
    {
        "name": "process_version",
        "path": "/Mgmt/ProcessVersion",
        "address": None,
        "length": 0,
        "regtype": MB_NONE,
        "encoding": "string",
        "default": "1.1",
        "on_error": ON_ERROR_KEEP,
    },
    {
        "name": "connection",
        "path": "/Mgmt/Connection",
        "address": None,
        "length": 0,
        "regtype": MB_NONE,
        "encoding": "string",
        "default": f"Modbus TCP {HOST}:{PORT}, unit {UNIT_ID}",
        "on_error": ON_ERROR_KEEP,
    },
    {
        "name": "product_name",
        "path": "/ProductName",
        "address": None,
        "length": 0,
        "regtype": MB_NONE,
        "encoding": None,
        "default": "Ecoforest Heat Pump",
        "on_error": ON_ERROR_KEEP,
    },
    {
        "name": "product_id",
        "path": "/ProductId",
        "address": None,
        "length": 0,
        "regtype": MB_NONE,
        "encoding": None,
        "default": 1234,
        "on_error": ON_ERROR_KEEP,
    },

    # Device information
    {
        "name": "firmware_version",
        "path": "/FirmwareVersion",
        "address": 9,
        "length": 3,
        "regtype": MB_NONE,
        "encoding": "ascii",
        "default": "1.0.0",
        "on_error": ON_ERROR_KEEP,
    },

    # Status
    {
        "name": "status_raw",
        "path": "/State",
        "address": 50,
        "length": 1,
        "regtype": MB_INPUTBOOL,
        "encoding": "u16",
        "default": 1,
        "on_error": ON_ERROR_DEFAULT,
        "map": {0: 1, 1: 0},
    },
    {
        "name": "temperature",
        "path": "/Temperature",
        "address": 17,
        "length": 1,
        "regtype": MB_INPUT,
        "encoding": "i16",
        "default": 0.0,
        "on_error": ON_ERROR_KEEP,
        "scale": 10.0,
    },
    {
        "name": "targettemperature",
        "path": "/TargetTemperature",
        "address": 134,
        "length": 1,
        "regtype": MB_INPUT,
        "encoding": "u16",
        "default": 0.0,
        "on_error": ON_ERROR_KEEP,
        "scale": 10.0,
    },

    # AC total
    {
        "name": "ac_power_total",
        "path": "/Ac/Power",
        "address": 5082,
        "length": 1,
        "regtype": MB_INPUT,
        "encoding": "i16",
        "default": 0.0,
        "on_error": ON_ERROR_KEEP,
        "scale": 1,
    },
    {
        "name": "total_energy",
        "path": "/Ac/Energy/Forward",
        "address": 5168,
        "length": 12,
        "regtype": MB_INPUT,
        "encoding": "i16sum",
        "default": 0.0,
        "on_error": ON_ERROR_KEEP,
        "scale": 1.0,
    },
]



def u32(registers, index):
    """Combine one or two 16-bit registers into unsigned integer."""
    if index + 1 >= len(registers):
        return registers[index]
    return (registers[index] << 16) + registers[index + 1]


def s32(registers, index):
    """Combine two 16-bit registers into signed 32-bit."""
    value = u32(registers, index)

    if value >= 0x80000000:
        value -= 0x100000000

    return value


def decode_ascii_registers(registers, start, count):
    """
    Decode Modbus registers containing ASCII characters.
    Each 16-bit register contains two ASCII bytes.
    """
    result = ""

    for i in range(start, start + count):
        value = registers[i]
        high = (value >> 8) & 0xFF
        low = value & 0xFF

        if high != 0:
            result += chr(high)

        if low != 0:
            result += chr(low)

    return result.strip()


def build_modbus_messages(regs):
    """
    Build a read plan per Modbus register type.

    For each register type, determine the first and last used address and split
    into messages of at most MAX_REGISTERS_PER_READ registers.
    """
    messages = []

    for regtype in (MB_INPUT, MB_HOLDING):
        typed_regs = [
            reg for reg in regs
            if reg["regtype"] == regtype and reg["address"] is not None
        ]

        if not typed_regs:
            continue

        first = min(reg["address"] for reg in typed_regs)
        last = max(reg["address"] + reg["length"] - 1 for reg in typed_regs)

        start = first
        while start <= last:
            end = min(start + MAX_REGISTERS_PER_READ - 1, last)
            messages.append({
                "regtype": regtype,
                "start": start,
                "count": end - start + 1,
            })
            start = end + 1

    return messages


def decode_value(reg, values):
    """Decode one REG item from the values dictionary."""
    start = reg["address"]
    length = reg["length"]
    registers = [values[start + offset] for offset in range(length)]

    if reg["encoding"] == "ascii":
        value = decode_ascii_registers(registers, 0, length)
    elif reg["encoding"] == "s32":
        value = s32(registers, 0)
    elif reg["encoding"] == "u32":
        value = u32(registers, 0)
    else:
        raise ValueError(f"Unsupported encoding {reg['encoding']}")

    if "map" in reg:
        value = reg["map"].get(value, reg["default"])

    if "scale" in reg and reg["scale"]:
        value = value / reg["scale"]

    return value



def get_supported_settings(regs):
    """Build SettingsDevice supportedSettings from REG entries."""
    supported = {}

    for reg in regs:
        if "setting" not in reg:
            continue

        supported[reg["setting"]] = [
            reg["setting_path"],
            reg["default"],
            reg.get("setting_min", 0),
            reg.get("setting_max", 0),
        ]

    return supported


def get_reg_default(reg, settings):
    """Return REG default, overridden by SettingsDevice when configured."""
    if "setting" not in reg:
        return reg["default"]

    value = settings[reg["setting"]]

    if "cast" in reg:
        try:
            value = reg["cast"](value)
        except Exception:
            logging.warning(
                "Invalid setting value for %s: %r, using default %r",
                reg["setting"],
                value,
                reg["default"],
            )
            value = reg["default"]

    return value


class EcoforestDbus:

    def __init__(self):
        service_name = f"com.victronenergy.heatpump.ecoforest_{DEVICE_INSTANCE}"
        self.bus = dbus.SystemBus()
        self.service = VeDbusService(service_name, register=False)
        self.modbus_messages = build_modbus_messages(REG)
        self.last_values = {}
        self.settings = SettingsDevice(
            self.bus,
            get_supported_settings(REG),
            self.handle_setting_changed,
        )

        # ====================================================
        # Device Information
        # ====================================================
        self.service.add_path("/Connected", 0)

        # ====================================================
        # REG
        # ====================================================
        added_paths = set()
        for reg in REG:
            if reg.get("internal"):
                continue
            for path in self.get_paths(reg):
                if path not in added_paths:
                    self.service.add_path(
                        path,
                        get_reg_default(reg, self.settings),
                        writeable=bool(reg.get("writeable")),
                        onchangecallback=self.set_setting_value if reg.get("writeable") else None,
                    )
                    added_paths.add(path)

        # ====================================================
        # Derived DBus paths
        # ====================================================

        self.write_default_values_for_none_registers()
        self.service.register()

    @staticmethod
    def get_paths(reg):
        path = reg["path"]
        if isinstance(path, (list, tuple)):
            return path
        return [path]

    def write_paths(self, reg, value):
        if reg.get("internal"):
            return
        for path in self.get_paths(reg):
            self.service[path] = value

    def write_default_values_for_none_registers(self):
        for reg in REG:
            if reg["regtype"] is MB_NONE:
                self.write_paths(reg, get_reg_default(reg, self.settings))

    def read_modbus_message(self, client, message):
        start = message["start"]
        count = message["count"]

        if message["regtype"] == MB_INPUT:
            rr = client.read_input_registers(start, count, unit=UNIT_ID)
        elif message["regtype"] == MB_HOLDING:
            rr = client.read_holding_registers(start, count, unit=UNIT_ID)
        else:
            raise ValueError(f"Unsupported Modbus register type {message['regtype']}")

        if rr.isError():
            raise RuntimeError(rr)

        return rr.registers

    def read_modbus_data(self):
        """Read all planned Modbus messages and return values per regtype/address."""
        data = {
            MB_INPUT: {},
            MB_HOLDING: {},
        }

        client = ModbusTcpClient(HOST, port=PORT, timeout=1)
        try:
            if not client.connect():
                raise RuntimeError("Modbus TCP connect failed")

            for message in self.modbus_messages:
                registers = self.read_modbus_message(client, message)
                for offset, value in enumerate(registers):
                    data[message["regtype"]][message["start"] + offset] = value

            return data
        finally:
            client.close()

    def apply_read_error_policy(self):
        """Apply per-register fallback behaviour after a Modbus read error."""
        for reg in REG:
            if reg["regtype"] is MB_NONE:
                self.write_paths(reg, get_reg_default(reg, self.settings))
                continue

            if reg["on_error"] == ON_ERROR_DEFAULT:
                self.write_paths(reg, reg["default"])
            # ON_ERROR_KEEP intentionally performs no DBus write action.

    def update_dbus_from_modbus(self, data):
        decoded = {}

        for reg in REG:
            if reg["regtype"] is MB_NONE:
                value = get_reg_default(reg, self.settings)
                self.write_paths(reg, value)
                decoded[reg["name"]] = value
                continue

            try:
                values = data[reg["regtype"]]
                value = decode_value(reg, values)
                decoded[reg["name"]] = value

                self.write_paths(reg, value)

            except Exception as e:
                logging.exception("Decode failed for %s: %s", reg["name"], e)
                decoded[reg["name"]] = reg["default"]
                if reg["on_error"] == ON_ERROR_DEFAULT:
                    self.write_paths(reg, reg["default"])

    def handle_setting_changed(self, setting, oldvalue, newvalue):
        """Update DBus when SettingsDevice changes externally."""
        reg = self.get_reg_by_setting(setting)
        if reg is None:
            return

        value = self.cast_reg_value(reg, newvalue)
        for path in self.get_paths(reg):
            self.service[path] = value

        logging.info(
            "Setting %s changed: %r -> %r",
            setting,
            oldvalue,
            value,
        )

    @staticmethod
    def get_reg_by_setting(setting):
        for reg in REG:
            if reg.get("setting") == setting:
                return reg
        return None

    @staticmethod
    def cast_reg_value(reg, value):
        if "cast" not in reg:
            return value

        try:
            return reg["cast"](value)
        except Exception:
            logging.warning(
                "Invalid value for %s: %r, using default %r",
                reg.get("setting", reg["name"]),
                value,
                reg["default"],
            )
            return reg["default"]

    def set_setting_value(self, path, value):
        """Persist writeable local DBus settings through SettingsDevice."""
        try:
            reg = next(
                reg for reg in REG
                if reg.get("writeable") and path in self.get_paths(reg)
            )
        except StopIteration:
            logging.error("No writeable REG setting found for %s", path)
            return False

        value = self.cast_reg_value(reg, value)
        self.settings[reg["setting"]] = value
        self.service[path] = value
        logging.info("Setting %s updated to %r", reg["setting"], value)
        return True

    def poll(self):
        try:
            data = self.read_modbus_data()
            self.update_dbus_from_modbus(data)
            self.service["/Connected"] = 1

        except Exception as e:
            logging.exception("Polling failed: %s", e)
            self.service["/Connected"] = 0
            self.apply_read_error_policy()

        return True


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )
    inverter = EcoforestDbus()
    GLib.timeout_add(POLL_INTERVAL_MS, inverter.poll)
    inverter.poll()
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
