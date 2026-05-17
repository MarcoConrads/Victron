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

DEVICE_INSTANCE = 40
POLL_INTERVAL_MS = 1000

POSITION = 1

MAX_POWER_W = 10000


# ============================================================
# Growatt Modbus Registers
# ============================================================

REG = {
    # Device information
    "product_id": 23,
    "firmware_version": 9,
    "hardware_version": 12,

    # Status
    "status": 0,
    "errorcode" : 105,

    # PV
    "pv1_voltage": 3,
    "pv1_current": 4,
    "pv1_power": 5,

    "pv2_voltage": 7,
    "pv2_current": 8,
    "pv2_power": 9,

    # AC total
    "ac_power_total": 35,
    "grid_freq": 37,
    "voltageRS": 50,
    "voltageST": 51,
    "voltageTR": 52,
    "maxpower": 6,

    # L1
    "l1_voltage": 38,
    "l1_current": 39,
    "l1_power": 40,

    # L2
    "l2_voltage": 42,
    "l2_current": 43,
    "l2_power": 44,

    # L3
    "l3_voltage": 46,
    "l3_current": 47,
    "l3_power": 48,

    # Energy
    "total_energy": 53,
}


# Holding register for total active power limit
REG_POWER_LIMIT_TOTAL = 3
POWER_LIMIT_SCALE = 100


def u32(registers, index):
    """
    Combine two 16-bit registers into unsigned 32-bit.
    """
    return (registers[index] << 16) + registers[index + 1]


def s32(registers, index):
    """
    Combine two 16-bit registers into signed 32-bit.
    """
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


class GrowattDbus:

    def __init__(self):

        service_name = (
            f"com.victronenergy.pvinverter.growatt_{DEVICE_INSTANCE}"
        )

        self.service = VeDbusService(service_name, register=False)

        # ====================================================
        # Management
        # ====================================================
        self.service.add_path("/Mgmt/ProcessName", __file__)
        self.service.add_path("/Mgmt/ProcessVersion", "1.0")
        self.service.add_path("/Mgmt/Connection",f"Modbus TCP {HOST}:{PORT}, unit {UNIT_ID}")
        self.service.add_path("/IsGenericEnergyMeter", 0)

        # ====================================================
        # Device Information
        # ====================================================
        self.service.add_path("/DeviceInstance", DEVICE_INSTANCE)
        self.service.add_path("/ProductName","Growatt 3-Phase Inverter")
        self.service.add_path("/ProductId", 0xA14A)
        self.service.add_path("/FirmwareVersion", "")
        self.service.add_path("/HardwareVersion", "")
        self.service.add_path("/Connected", 0)
        self.service.add_path("/Position", POSITION)

        # ====================================================
        # Total AC
        # ====================================================
        self.service.add_path("/Ac/Power", 0.0)
        self.service.add_path("/Ac/Current", 0.0)
        self.service.add_path("/Ac/Voltage", 0.0)
        self.service.add_path("/Ac/Energy/Forward", 0.0)
        self.service.add_path("/Ac/MaxPower", 0.0)

        # ====================================================
        # AC L1
        # ====================================================
        self.service.add_path("/Ac/L1/Voltage", 0.0)
        self.service.add_path("/Ac/L1/Current", 0.0)
        self.service.add_path("/Ac/L1/Power", 0.0)
        self.service.add_path("/Ac/L1/Energy/Forward", 0.0)
        self.service.add_path("/Ac/L1/Frequency", 0.0)

        # ====================================================
        # AC L2
        # ====================================================
        self.service.add_path("/Ac/L2/Voltage", 0.0)
        self.service.add_path("/Ac/L2/Current", 0.0)
        self.service.add_path("/Ac/L2/Power", 0.0)
        self.service.add_path("/Ac/L2/Energy/Forward", 0.0)
        self.service.add_path("/Ac/L2/Frequency", 0.0)

        # ====================================================
        # AC L3
        # ====================================================
        self.service.add_path("/Ac/L3/Voltage", 0.0)
        self.service.add_path("/Ac/L3/Current", 0.0)
        self.service.add_path("/Ac/L3/Power", 0.0)
        self.service.add_path("/Ac/L3/Energy/Forward", 0.0)
        self.service.add_path("/Ac/L3/Frequency", 0.0)

        # ====================================================
        # DC Inputs
        # ====================================================
        self.service.add_path("/Dc/0/Voltage", 0.0)
        self.service.add_path("/Dc/0/Current", 0.0)
        self.service.add_path("/Dc/0/Power", 0.0)

        self.service.add_path("/Dc/1/Voltage", 0.0)
        self.service.add_path("/Dc/1/Current", 0.0)
        self.service.add_path("/Dc/1/Power", 0.0)

        # ====================================================
        # Status
        # ====================================================
        self.service.add_path("/StatusCode", 0)
        self.service.add_path("/ErrorCode", 0)

        # ====================================================
        # Writable Total Power Limit
        # ====================================================
        self.service.add_path("/Ac/PowerLimit",0.0,writeable=True,onchangecallback=self.set_power_limit)

        self.service.register()

    def read_input_registers(self, start, count):

        client = ModbusTcpClient(HOST, port=PORT, timeout=3)
        try:
            if not client.connect():
                raise RuntimeError("Modbus TCP connect failed")
            rr = client.read_input_registers(start, count, unit=UNIT_ID)
            if rr.isError():
                raise RuntimeError(rr)
            return rr.registers
        finally:
            client.close()

    def read_holding_registers(self, start, count):

        client = ModbusTcpClient(HOST, port=PORT, timeout=3)
        try:
            if not client.connect():
                raise RunTimeError("Modbus TCP connect failed")
            rr = client.read_holding_registers(start, count,unit=UNIT_ID)
            if rr.isError():
                raise RuntimeError(rr)
            return rr.registers
        finally:
            client.close()

    def set_power_limit(self, path, value):

        try:
            watts = int(float(value))

            if watts < 0:
                watts = 0

            if watts > MAX_POWER_W:
                watts = MAX_POWER_W

            register_value = int(
                watts / POWER_LIMIT_SCALE
            )

            client = ModbusTcpClient(HOST, port=PORT, timeout=3)

            if not client.connect():
                logging.error(
                    "Unable to connect to inverter"
                )
                return False

            rr = client.write_register(
                REG_POWER_LIMIT_TOTAL,
                register_value,
                unit=UNIT_ID
            )

            client.close()

            if rr.isError():
                logging.error(
                    "Failed to write power limit: %s",
                    rr
                )
                return False

            self.service["/Ac/PowerLimit"] = watts

            logging.info(
                "3-phase power limit set to %s W",
                watts
            )

            return True

        except Exception as e:

            logging.exception(
                "Power limit update failed: %s",
                e
            )

            return False

    def poll(self):

        try:

            registers = self.read_input_registers(0, 125)
            holding = self.read_holding_registers(0, 125)

            # ====================================================
            # Device info
            # ====================================================
            # product_id = decode_ascii_registers(holding,REG["product_id"],5)
            firmware_version = decode_ascii_registers(holding,REG["firmware_version"],3)
            hardware_version = decode_ascii_registers(holding,REG["hardware_version"],3)

            # ====================================================
            # Status
            # ====================================================
            statusGrowatt = registers[REG["status"]]
            if statusGrowatt == 0: # waiting
                status = 0
            elif statusGrowatt == 1: #normal
                status = 7
            elif statusGrowatt == 3: #fault
                status = 10

            maxpower = u32(holding,REG["maxpower"]) / 10.0
            errorcode = registers[REG["errorcode"]]

            # ====================================================
            # PV Inputs
            # ====================================================
            pv1_voltage = registers[REG["pv1_voltage"]] / 10.0
            pv1_current = registers[REG["pv1_current"]] / 10.
            pv1_power = s32(registers, REG["pv1_power"]) / 10.0

            pv2_voltage = registers[REG["pv2_voltage"]] / 10.0
            pv2_current = registers[REG["pv2_current"]] / 10.0
            pv2_power = s32(registers, REG["pv2_power"]) / 10.0

            # ====================================================
            # Grid Frequency
            # ====================================================
            frequency = registers[REG["grid_freq"]] / 100.0
            voltageRS = registers[REG["voltageRS"]] / 10.0
            voltageST = registers[REG["voltageST"]] / 10.0
            voltageTR = registers[REG["voltageTR"]] / 10.0
            voltage = (voltageRS + voltageST + voltageTR) / 3.0

            # ====================================================
            # Phase L1
            # ====================================================
            l1_voltage = registers[REG["l1_voltage"]] / 10.0
            l1_current = registers[REG["l1_current"]] / 10.0
            l1_power = s32(registers, REG["l1_power"]) / 10.0

            # ====================================================
            # Phase L2
            # ====================================================
            l2_voltage = registers[REG["l2_voltage"]] / 10.0
            l2_current = registers[REG["l2_current"]] / 10.0
            l2_power = s32(registers, REG["l2_power"]) / 10.0
            
            # ====================================================
            # Phase L3
            # ====================================================
            l3_voltage = registers[REG["l3_voltage"]] / 10.0
            l3_current = registers[REG["l3_current"]] / 10.0
            l3_power = s32(registers, REG["l3_power"]) / 10.0

            # ====================================================
            # Total Power
            # ====================================================
            total_power = s32(registers, REG["ac_power_total"]) / 10.0
            total_energy = u32(registers, REG["total_energy"]) / 10.0
            phase_energy = total_energy / 3.0
            current = (l1_current + l2_current + l3_current) / 3.0

            # ====================================================
            # Update D-Bus
            # ====================================================
            # self.service["/ProductId"] = product_id
            self.service["/FirmwareVersion"] = firmware_version
            self.service["/HardwareVersion"] = hardware_version
            self.service["/Connected"] = 1
            self.service["/StatusCode"] = status
            self.service["/ErrorCode"] = errorcode

            # PV1
            self.service["/Dc/0/Voltage"] = pv1_voltage
            self.service["/Dc/0/Current"] = pv1_current
            self.service["/Dc/0/Power"] = pv1_power

            # PV2
            self.service["/Dc/1/Voltage"] = pv2_voltage
            self.service["/Dc/1/Current"] = pv2_current
            self.service["/Dc/1/Power"] = pv2_power

            # Total AC
            self.service["/Ac/Power"] = total_power
            self.service["/Ac/Energy/Forward"] = total_energy
            self.service["/Ac/Current"] = current
            self.service["/Ac/Voltage"] = voltage
            self.service["/Ac/MaxPower"] = maxpower 

            # L1
            self.service["/Ac/L1/Voltage"] = l1_voltage
            self.service["/Ac/L1/Current"] = l1_current
            self.service["/Ac/L1/Power"] = l1_power
            self.service["/Ac/L1/Energy/Forward"] = phase_energy
            self.service["/Ac/L1/Frequency"] = frequency

            # L2
            self.service["/Ac/L2/Voltage"] = l2_voltage
            self.service["/Ac/L2/Current"] = l2_current
            self.service["/Ac/L2/Power"] = l2_power
            self.service["/Ac/L2/Energy/Forward"] = phase_energy
            self.service["/Ac/L2/Frequency"] = frequency

            # L3
            self.service["/Ac/L3/Voltage"] = l3_voltage
            self.service["/Ac/L3/Current"] = l3_current
            self.service["/Ac/L3/Power"] = l3_power
            self.service["/Ac/L3/Energy/Forward"] = phase_energy
            self.service["/Ac/L3/Frequency"] = frequency

        except Exception as e:

            logging.exception(
                "Polling failed: %s",
                e
            )

            self.service["/Connected"] = 0

        return True



def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    inverter = GrowattDbus()
    GLib.timeout_add(POLL_INTERVAL_MS, inverter.poll)
    inverter.poll()
    GLib.MainLoop().run()

if __name__ == "__main__":
    main()
