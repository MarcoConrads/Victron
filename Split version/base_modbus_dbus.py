import logging

import dbus
from pymodbus.client.sync import ModbusTcpClient
from settingsdevice import SettingsDevice
from vedbus import VeDbusService

from modbus_codec import ModbusValueCodec, get_supported_settings, get_reg_default
from modbus_types import (
    BINARY_TYPES,
    MAX_BITS_PER_READ,
    MAX_REGISTERS_PER_READ,
    MB_COIL,
    MB_HOLDING_REGISTER,
    MB_INPUT_BINARY,
    MB_INPUT_REGISTER,
    MB_NONE,
    MODBUS_TYPES,
    ON_ERROR_DEFAULT,
    REGISTER_TYPES,
)

class BaseModbusDbus:
    """Base class with generic DBus, Modbus read and decode behaviour."""

    regs = []
    host = HOST
    port = PORT
    unit_id = UNIT_ID
    service_name = None

    def __init__(self):
        if not self.service_name:
            raise ValueError("service_name must be set by subclass")

        self.bus = dbus.SystemBus()
        self.service = VeDbusService(self.service_name, register=False)
        self.modbus_messages = self.build_modbus_messages(self.regs)
        self.last_values = {}
        self.settings = SettingsDevice(
            self.bus,
            get_supported_settings(self.regs),
            self.handle_setting_changed,
        )

        self.service.add_path("/Connected", 0)
        self.add_reg_paths()
        self.add_extra_paths()
        self.write_default_values_for_none_registers()
        self.service.register()

    @staticmethod
    def get_paths(reg):
        path = reg["path"]
        if isinstance(path, (list, tuple)):
            return path
        return [path]

    @staticmethod
    def max_items_for_regtype(regtype):
        if regtype in BINARY_TYPES:
            return MAX_BITS_PER_READ
        if regtype in REGISTER_TYPES:
            return MAX_REGISTERS_PER_READ
        raise ValueError(f"Unsupported Modbus type {regtype}")

    @classmethod
    def build_modbus_messages(cls, regs):
        """Build a read plan per Modbus type."""
        messages = []

        for regtype in MODBUS_TYPES:
            typed_regs = [
                reg for reg in regs
                if reg["regtype"] == regtype and reg["address"] is not None
            ]

            if not typed_regs:
                continue

            first = min(reg["address"] for reg in typed_regs)
            last = max(reg["address"] + reg["length"] - 1 for reg in typed_regs)
            max_items = cls.max_items_for_regtype(regtype)

            start = first
            while start <= last:
                end = min(start + max_items - 1, last)
                messages.append({
                    "regtype": regtype,
                    "start": start,
                    "count": end - start + 1,
                })
                start = end + 1

        return messages

    def add_reg_paths(self):
        added_paths = set()
        for reg in self.regs:
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

    def add_extra_paths(self):
        """Hook for subclass-specific extra DBus paths."""

    def write_paths(self, reg, value):
        if reg.get("internal"):
            return
        for path in self.get_paths(reg):
            self.service[path] = value

    def write_default_values_for_none_registers(self):
        for reg in self.regs:
            if reg["regtype"] is MB_NONE:
                self.write_paths(reg, get_reg_default(reg, self.settings))

    def read_modbus_message(self, client, message):
        start = message["start"]
        count = message["count"]
        regtype = message["regtype"]

        if regtype == MB_COIL:
            rr = client.read_coils(start, count, unit=self.unit_id)
        elif regtype == MB_INPUT_BINARY:
            rr = client.read_discrete_inputs(start, count, unit=self.unit_id)
        elif regtype == MB_INPUT_REGISTER:
            rr = client.read_input_registers(start, count, unit=self.unit_id)
        elif regtype == MB_HOLDING_REGISTER:
            rr = client.read_holding_registers(start, count, unit=self.unit_id)
        else:
            raise ValueError(f"Unsupported Modbus type {regtype}")

        if rr.isError():
            raise RuntimeError(rr)

        if regtype in BINARY_TYPES:
            return [1 if bit else 0 for bit in rr.bits[:count]]

        return rr.registers

    def read_modbus_data(self):
        """Read all planned Modbus messages and return values per regtype/address."""
        data = {regtype: {} for regtype in MODBUS_TYPES}

        client = ModbusTcpClient(self.host, port=self.port, timeout=1)
        try:
            if not client.connect():
                raise RuntimeError("Modbus TCP connect failed")

            for message in self.modbus_messages:
                values = self.read_modbus_message(client, message)
                for offset, value in enumerate(values):
                    data[message["regtype"]][message["start"] + offset] = value

            return data
        finally:
            client.close()

    def apply_read_error_policy(self):
        """Apply per-register fallback behaviour after a Modbus read error."""
        for reg in self.regs:
            if reg["regtype"] is MB_NONE:
                self.write_paths(reg, get_reg_default(reg, self.settings))
                continue

            if reg["on_error"] == ON_ERROR_DEFAULT:
                self.write_paths(reg, reg["default"])
            # ON_ERROR_KEEP intentionally performs no DBus write action.

    def update_dbus_from_modbus(self, data):
        decoded = {}

        for reg in self.regs:
            if reg["regtype"] is MB_NONE:
                value = get_reg_default(reg, self.settings)
                self.write_paths(reg, value)
                decoded[reg["name"]] = value
                continue

            try:
                values = data[reg["regtype"]]
                value = ModbusValueCodec.decode(reg, values)
                decoded[reg["name"]] = value
                self.write_paths(reg, value)

            except Exception as e:
                logging.exception("Decode failed for %s: %s", reg["name"], e)
                decoded[reg["name"]] = reg["default"]
                if reg["on_error"] == ON_ERROR_DEFAULT:
                    self.write_paths(reg, reg["default"])

        self.after_modbus_update(decoded)

    def after_modbus_update(self, decoded):
        """Hook for subclass-specific derived values."""

    def handle_setting_changed(self, setting, oldvalue, newvalue):
        """Update DBus when SettingsDevice changes externally."""
        reg = self.get_reg_by_setting(setting)
        if reg is None:
            return

        value = self.cast_reg_value(reg, newvalue)
        for path in self.get_paths(reg):
            self.service[path] = value

        logging.info("Setting %s changed: %r -> %r", setting, oldvalue, value)

    def get_reg_by_setting(self, setting):
        for reg in self.regs:
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
                reg for reg in self.regs
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
