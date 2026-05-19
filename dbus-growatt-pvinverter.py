#!/usr/bin/env python3
# /data/dbus-growatt/dbus_growatt.py

import sys
import logging
from gi.repository import GLib
import dbus.mainloop.glib

sys.path.insert(0, "/opt/victronenergy/dbus-systemcalc-py/ext/velib_python")
sys.path.insert(0, "/data/velib_python")

from vedbus import VeDbusService
from pymodbus.client.sync import ModbusTcpClient

# ============================================================
# Configuration
# ============================================================

HOST = "192.168.11.68"
PORT = 502
UNIT_ID = 2

DEVICE_INSTANCE = 48
POLL_INTERVAL_MS = 1000

POSITION = 1

DEFAULT_MAX_POWER_W = 10000

# Modbus register types
MB_INPUT = "input"
MB_HOLDING = "holding"
MB_NONE = None

# Behaviour on Modbus read error
ON_ERROR_DEFAULT = "default"
ON_ERROR_KEEP = "keep"

MAX_REGISTERS_PER_READ = 125

# Holding register for total active power limit.
# The register expects a value from 0 to 100 percent.
REG_POWER_LIMIT_TOTAL = 3


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
    # Device information
    {
        "name": "firmware_version",
        "path": "/FirmwareVersion",
        "address": 9,
        "length": 3,
        "regtype": MB_HOLDING,
        "encoding": "ascii",
        "default": "",
        "on_error": ON_ERROR_KEEP,
    },
    {
        "name": "hardware_version",
        "path": "/HardwareVersion",
        "address": 12,
        "length": 3,
        "regtype": MB_HOLDING,
        "encoding": "ascii",
        "default": "",
        "on_error": ON_ERROR_KEEP,
    },

    # Status
    {
        "name": "status_raw",
        "path": "/StatusCode",
        "address": 0,
        "length": 1,
        "regtype": MB_INPUT,
        "encoding": "u32",
        "default": 0,
        "on_error": ON_ERROR_DEFAULT,
        "map": {0: 0, 1: 7, 3: 10},
    },
    {
        "name": "errorcode",
        "path": "/ErrorCode",
        "address": 105,
        "length": 1,
        "regtype": MB_INPUT,
        "encoding": "u32",
        "default": 0,
        "on_error": ON_ERROR_DEFAULT,
    },

    # PV input 1
    {
        "name": "pv1_voltage",
        "path": "/Dc/0/Voltage",
        "address": 3,
        "length": 1,
        "regtype": MB_INPUT,
        "encoding": "u32",
        "default": 0.0,
        "on_error": ON_ERROR_DEFAULT,
        "scale": 10.0,
    },
    {
        "name": "pv1_current",
        "path": "/Dc/0/Current",
        "address": 4,
        "length": 1,
        "regtype": MB_INPUT,
        "encoding": "u32",
        "default": 0.0,
        "on_error": ON_ERROR_DEFAULT,
        "scale": 10.0,
    },
    {
        "name": "pv1_power",
        "path": "/Dc/0/Power",
        "address": 5,
        "length": 2,
        "regtype": MB_INPUT,
        "encoding": "s32",
        "default": 0.0,
        "on_error": ON_ERROR_DEFAULT,
        "scale": 10.0,
    },

    # PV input 2
    {
        "name": "pv2_voltage",
        "path": "/Dc/1/Voltage",
        "address": 7,
        "length": 1,
        "regtype": MB_INPUT,
        "encoding": "u32",
        "default": 0.0,
        "on_error": ON_ERROR_DEFAULT,
        "scale": 10.0,
    },
    {
        "name": "pv2_current",
        "path": "/Dc/1/Current",
        "address": 8,
        "length": 1,
        "regtype": MB_INPUT,
        "encoding": "u32",
        "default": 0.0,
        "on_error": ON_ERROR_DEFAULT,
        "scale": 10.0,
    },
    {
        "name": "pv2_power",
        "path": "/Dc/1/Power",
        "address": 9,
        "length": 2,
        "regtype": MB_INPUT,
        "encoding": "s32",
        "default": 0.0,
        "on_error": ON_ERROR_DEFAULT,
        "scale": 10.0,
    },

    # AC total
    {
        "name": "ac_power_total",
        "path": "/Ac/Power",
        "address": 35,
        "length": 2,
        "regtype": MB_INPUT,
        "encoding": "s32",
        "default": 0.0,
        "on_error": ON_ERROR_DEFAULT,
        "scale": 10.0,
    },
    {
        "name": "total_energy",
        "path": "/Ac/Energy/Forward",
        "address": 53,
        "length": 2,
        "regtype": MB_INPUT,
        "encoding": "u32",
        "default": 0.0,
        "on_error": ON_ERROR_KEEP,
        "scale": 10.0,
    },
    {
        "name": "maxpower",
        "path": "/Ac/MaxPower",
        "address": 6,
        "length": 2,
        "regtype": MB_HOLDING,
        "encoding": "u32",
        "default": 0.0,
        "on_error": ON_ERROR_KEEP,
        "scale": 10.0,
    },

    {
        "name": "power_limit_percent",
        "path": "/Ac/PowerLimit",
        "address": REG_POWER_LIMIT_TOTAL,
        "length": 1,
        "regtype": MB_HOLDING,
        "encoding": "u32",
        "default": 0.0,
        "on_error": ON_ERROR_KEEP,
        "internal": True,
    },

    # Grid / phase values used directly or for derived DBus values
    {
        "name": "grid_freq",
        "path": [
            "/Ac/L1/Frequency",
            "/Ac/L2/Frequency",
            "/Ac/L3/Frequency",
        ],
        "address": 37,
        "length": 1,
        "regtype": MB_INPUT,
        "encoding": "u32",
        "default": 0.0,
        "on_error": ON_ERROR_DEFAULT,
        "scale": 100.0,
    },
    {
        "name": "l1_voltage",
        "path": "/Ac/L1/Voltage",
        "address": 38,
        "length": 1,
        "regtype": MB_INPUT,
        "encoding": "u32",
        "default": 0.0,
        "on_error": ON_ERROR_DEFAULT,
        "scale": 10.0,
    },
    {
        "name": "l1_current",
        "path": "/Ac/L1/Current",
        "address": 39,
        "length": 1,
        "regtype": MB_INPUT,
        "encoding": "u32",
        "default": 0.0,
        "on_error": ON_ERROR_DEFAULT,
        "scale": 10.0,
    },
    {
        "name": "l1_power",
        "path": "/Ac/L1/Power",
        "address": 40,
        "length": 2,
        "regtype": MB_INPUT,
        "encoding": "s32",
        "default": 0.0,
        "on_error": ON_ERROR_DEFAULT,
        "scale": 10.0,
    },
    {
        "name": "l2_voltage",
        "path": "/Ac/L2/Voltage",
        "address": 42,
        "length": 1,
        "regtype": MB_INPUT,
        "encoding": "u32",
        "default": 0.0,
        "on_error": ON_ERROR_DEFAULT,
        "scale": 10.0,
    },
    {
        "name": "l2_current",
        "path": "/Ac/L2/Current",
        "address": 43,
        "length": 1,
        "regtype": MB_INPUT,
        "encoding": "u32",
        "default": 0.0,
        "on_error": ON_ERROR_DEFAULT,
        "scale": 10.0,
    },
    {
        "name": "l2_power",
        "path": "/Ac/L2/Power",
        "address": 44,
        "length": 2,
        "regtype": MB_INPUT,
        "encoding": "s32",
        "default": 0.0,
        "on_error": ON_ERROR_DEFAULT,
        "scale": 10.0,
    },
    {
        "name": "l3_voltage",
        "path": "/Ac/L3/Voltage",
        "address": 46,
        "length": 1,
        "regtype": MB_INPUT,
        "encoding": "u32",
        "default": 0.0,
        "on_error": ON_ERROR_DEFAULT,
        "scale": 10.0,
    },
    {
        "name": "l3_current",
        "path": "/Ac/L3/Current",
        "address": 47,
        "length": 1,
        "regtype": MB_INPUT,
        "encoding": "u32",
        "default": 0.0,
        "on_error": ON_ERROR_DEFAULT,
        "scale": 10.0,
    },
    {
        "name": "l3_power",
        "path": "/Ac/L3/Power",
        "address": 48,
        "length": 2,
        "regtype": MB_INPUT,
        "encoding": "s32",
        "default": 0.0,
        "on_error": ON_ERROR_DEFAULT,
        "scale": 10.0,
    },


    # Paths without a Modbus register. These always write their default value.
    {
        "name": "is_generic_energy_meter",
        "path": "/IsGenericEnergyMeter",
        "address": None,
        "length": 0,
        "regtype": MB_NONE,
        "encoding": "u32",
        "default": 0,
        "on_error": ON_ERROR_DEFAULT,
    },
    {
        "name": "product_name",
        "path": "/ProductName",
        "address": None,
        "length": 0,
        "regtype": MB_NONE,
        "encoding": "ascii",
        "default": "Growatt 3-Phase Inverter",
        "on_error": ON_ERROR_DEFAULT,
    },
    {
        "name": "product_id_default",
        "path": "/ProductId",
        "address": None,
        "length": 0,
        "regtype": MB_NONE,
        "encoding": "u32",
        "default": 0xA14A,
        "on_error": ON_ERROR_DEFAULT,
    },
    {
        "name": "position",
        "path": "/Position",
        "address": None,
        "length": 0,
        "regtype": MB_NONE,
        "encoding": "u32",
        "default": POSITION,
        "on_error": ON_ERROR_DEFAULT,
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


class GrowattDbus:

    def __init__(self):
        service_name = f"com.victronenergy.pvinverter.growatt_{DEVICE_INSTANCE}"
        self.service = VeDbusService(service_name, register=False)
        self.modbus_messages = build_modbus_messages(REG)
        self.last_values = {}
        self.max_power_w = DEFAULT_MAX_POWER_W

        # ====================================================
        # Management
        # ====================================================
        self.service.add_path("/Mgmt/ProcessName", __file__)
        self.service.add_path("/Mgmt/ProcessVersion", "1.1")
        self.service.add_path(
            "/Mgmt/Connection",
            f"Modbus TCP {HOST}:{PORT}, unit {UNIT_ID}",
        )

        # ====================================================
        # Product information based on Fronius DBus service, but with some fields left empty or with default values.
        # ====================================================
        self.service.add_path("/Ac/NumberOfPhases", 3)
        self.service.add_path("/CustomName", "")
        self.service.add_path("/DataManagerVersion", "1.2.3.4.5.6")
        self.service.add_path("/FroniusDeviceType", 73)
        self.service.add_path("/Info/LimiterModel", 123)
        self.service.add_path("/Info/MeasurementModel", 113)

        # ====================================================
        # Device Information
        # ====================================================
        self.service.add_path("/DeviceInstance", DEVICE_INSTANCE)
        self.service.add_path("/Connected", 0)

        # Add all DBus paths from REG. A path may be a string or a list.
        added_paths = set()
        for reg in REG:
            if reg.get("internal"):
                continue
            for path in self.get_paths(reg):
                if path not in added_paths:
                    self.service.add_path(path, reg["default"])
                    added_paths.add(path)

        # ====================================================
        # Derived DBus paths
        # ====================================================
        self.service.add_path("/Ac/L1/Energy/Forward", 0.0)
        self.service.add_path("/Ac/L2/Energy/Forward", 0.0)
        self.service.add_path("/Ac/L3/Energy/Forward", 0.0)

        # ====================================================
        # Writable Total Power Limit
        # ====================================================
        self.service.add_path(
            "/Ac/PowerLimit",
            0.0,
            writeable=True,
            onchangecallback=self.set_power_limit,
        )

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
                self.write_paths(reg, reg["default"])

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

        client = ModbusTcpClient(HOST, port=PORT, timeout=3)
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
                self.write_paths(reg, reg["default"])
                continue

            if reg["on_error"] == ON_ERROR_DEFAULT:
                self.write_paths(reg, reg["default"])
            # ON_ERROR_KEEP intentionally performs no DBus write action.

    def update_dbus_from_modbus(self, data):
        decoded = {}

        for reg in REG:
            if reg["regtype"] is MB_NONE:
                self.write_paths(reg, reg["default"])
                decoded[reg["name"]] = reg["default"]
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

            client = ModbusTcpClient(HOST, port=PORT, timeout=3)

            try:
                if not client.connect():
                    logging.error("Unable to connect to inverter")
                    return False

                rr = client.write_register(
                    REG_POWER_LIMIT_TOTAL,
                    register_value,
                    unit=UNIT_ID,
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
    inverter = GrowattDbus()
    GLib.timeout_add(POLL_INTERVAL_MS, inverter.poll)
    inverter.poll()
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
