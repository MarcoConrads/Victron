from __future__ import annotations

from enum import IntEnum

import device
import mdns
import probe
from register import Reg_text, Reg_u16, Reg_u32b, Reg_s32b, Reg_s64b, Reg_e16

# Re-use Victron EV charger semantics (subset)
class EVC_CHARGE(IntEnum):
    DISABLED = 0
    ENABLED = 1

class EVC_MODE(IntEnum):
    MANUAL = 0
    AUTO = 1
    SCHEDULED = 2

class EVC_STATUS(IntEnum):
    DISCONNECTED = 0
    CONNECTED = 1
    CHARGING = 2
    CHARGED = 3
    WAIT_SUN = 4
    WAIT_RFID = 5
    WAIT_START = 6
    LOW_SOC = 7
    GND_ERROR = 8
    WELD_CON = 9
    CP_SHORTED = 10
    EARTH_LEAKAGE = 11
    UNDERVOLTAGE = 12
    OVERVOLTAGE = 13
    OVERTEMPERATURE = 14
    FAULT = 15

class PeblarModeReg(Reg_u16):
    """
    Virtual writable /Mode register stored on D-Bus only.
    """

    def decode(self, values):
        self.value = int(EVC_MODE.MANUAL)
        self.valid = True
        return True

class PeblarMaxCurentReg(Reg_u32b):

    def decode(self, values):
        self.value = int(16)
        self.valid = True
        return True

class PeblarCpStatusReg(Reg_u16):
    '''
    Peblar CpState is documented as a 'char' stored in uint16, values A/B/C/D/E/F/I/U. :contentReference[oaicite:5]{index=5}
    We convert it into Victron-like EVC_STATUS enum integers.
    '''

    def decode(self, values):
        if not values or values[0] is None:
            return False

        raw = int(values[0]) & 0xFFFF
        try:
            c = chr(raw)
        except Exception:
            c = 'U'

        # Mapping based on Peblar definitions:
        # A: no EV, B: connected suspended, C/D: charging, E/F/I: error/fault, U: unknown :contentReference[oaicite:6]{index=6}
        if c == 'A':
            self.value = int(EVC_STATUS.DISCONNECTED)
        elif c == 'B':
            self.value = int(EVC_STATUS.CONNECTED)
        elif c in ('C', 'D'):
            self.value = int(EVC_STATUS.CHARGING)
        elif c in ('E', 'F', 'I'):
            self.value = int(EVC_STATUS.FAULT)
        else:
            # Unknown -> treat as connected (safer than disconnected)
            self.value = int(EVC_STATUS.CONNECTED)

        self.valid = True
        return True


class PeblarStartStopReg(Reg_u32b):
    '''
    Expose /StartStop as 0/1 on D-Bus, while underlying control is ChargeCurrentLimit (mA) at register 40000. :contentReference[oaicite:7]{index=7}
    - read: if limit > 0 => ENABLED else DISABLED
    - write: 0 => write 0mA ; 1 => restore last set current (or 6A default)
    '''
    def __init__(self, base, name, scale=1000, text=None, write=None, access=None):
        super().__init__(base, name, scale=scale, text=text, write=write, access=access)
        self._last_nonzero_ma = 6000  # Peblar minimum to start charging is 6000mA. :contentReference[oaicite:8]{index=8}

    def decode(self, values):
        ok = super().decode(values)
        if not ok or self.value is None:
            return ok

        # super().decode gives A (because scale=1000), but we need to infer enabled/disabled
        # We can reconstruct mA from the raw decoded value * 1000.
        try:
            current_a = float(self.value)
        except Exception:
            current_a = 0.0

        current_ma = int(round(current_a * 1000.0))
        if current_ma > 0:
            self._last_nonzero_ma = max(self._last_nonzero_ma, current_ma)

        self.value = int(EVC_CHARGE.ENABLED if current_ma > 0 else EVC_CHARGE.DISABLED)
        self.valid = True
        return True

    def _write_startstop(self, device_obj: device.ModbusDevice, val: int) -> bool:
        try:
            v = int(val)
        except Exception:
            return False

        if v == int(EVC_CHARGE.DISABLED):
            device_obj.write_register(self, 0)  # 0 A => 0mA => pause :contentReference[oaicite:9]{index=9}
            return True

        if v == int(EVC_CHARGE.ENABLED):
            # restore last non-zero, or default 6A (6000mA)
            restore_ma = max(6000, int(self._last_nonzero_ma))
            restore_a = restore_ma / 1000.0
            device_obj.write_register(self, restore_a)
            return True

        return False


class PeblarEVCharger(device.ModbusDevice):
    '''
    Peblar Modbus TCP server (port 502) with big-endian words/bytes. :contentReference[oaicite:10]{index=10}
    Control register:
      - 40000 ChargeCurrentLimit (mA, uint32) for start/pause and setting current. :contentReference[oaicite:11]{index=11}
    Status registers:
      - 30110 CpState (char in uint16) :contentReference[oaicite:12]{index=12}
      - 30113 ChargeCurrentLimitActual (mA, uint32) :contentReference[oaicite:13]{index=13}
    Metering (Input registers):
      - 30000 EnergyTotal (Wh, int64) :contentReference[oaicite:14]{index=14}
      - 30004 SessionEnergy (Wh, int64) :contentReference[oaicite:15]{index=15}
      - 30008..30026 power/voltage/current per phase (W/V/mA, int32) :contentReference[oaicite:16]{index=16}
    System info (Input):
      - 30050 ProductSn string24 :contentReference[oaicite:17]{index=17}
      - 30062 ProductPn string24 :contentReference[oaicite:18]{index=18}
      - 30074 FirmwareVersion string24 :contentReference[oaicite:19]{index=19}
      - 30092 PhaseCount uint16 :contentReference[oaicite:20]{index=20}
    '''

    vendor_id = 'peblar'
    vendor_name = 'Peblar'
    device_type = 'EV charger'

    allowed_roles = None
    default_role = 'evcharger'
    default_instance = 40
    default_access = 'input'

    # Arbitrary product id for “custom” device
    productid = 0xB0B1
    productname = 'Peblar EV Charger'
    model = 'Peblar (Modbus TCP)'

    min_timeout = 0.5

    def device_init(self):
        # --- Info regs (Input register map) ---
        # string24 -> 24 bytes -> 12 registers (2 bytes/register)
        self.info_regs = [
            Reg_text(30050, 12, '/Serial', encoding='utf-8', access='input'),
            Reg_text(30062, 12, '/ProductPn', encoding='utf-8', access='input'),
            Reg_text(30074, 12, '/FirmwareVersion', encoding='utf-8', access='input'),
            Reg_u16(30092, '/PhaseCount', access='input'),
        ]

        # --- Control + status (Holding register map) ---
        # ChargeCurrentLimit: uint32 mA at 40000. :contentReference[oaicite:21]{index=21}
        # Expose as:
        #   /SetCurrent in A (writeable)
        #   /MaxCurrent in A (writeable) - alias to /SetCurrent for UI compatibility
        set_current = Reg_u32b(40000, '/SetCurrent', 1000, '%.1f A', write=True, access='holding')
        max_current = PeblarMaxCurentReg(40000, '/MaxCurrent', 1000, '%.1f A', write=True, access='holding')

        # /StartStop based on same 40000 register, with custom write behavior
        start_stop = PeblarStartStopReg(40000, '/StartStop', scale=1000, text='%d', access='holding')

        # We'll attach a callable write handler later once 'self' is available

        #max_current = PeblarMaxCurentReg(30022, '/MaxCurrent', 1000, '%.1f A', access='input')

        self.data_regs = [
            # Metering (Input register map) :contentReference[oaicite:22]{index=22}
            Reg_s32b(30008, '/Ac/L1/Power', 1, '%d W', access='input'),
            Reg_s32b(30010, '/Ac/L2/Power', 1, '%d W', access='input'),
            Reg_s32b(30012, '/Ac/L3/Power', 1, '%d W', access='input'),
            Reg_s32b(30014, '/Ac/Power', 1, '%d W', access='input'),

            Reg_s32b(30016, '/Ac/L1/Voltage', 1, '%d V', access='input'),
            Reg_s32b(30018, '/Ac/L2/Voltage', 1, '%d V', access='input'),
            Reg_s32b(30020, '/Ac/L3/Voltage', 1, '%d V', access='input'),

            # Peblar currents are mA (int32) -> expose as A
            Reg_s32b(30022, '/Current', 1000, '%.2f A', access='input'),
            # Reg_s32b(30024, '/Ac/L2/Current', 1000, '%.2f A', access='input'),
            # Reg_s32b(30026, '/Ac/L3/Current', 1000, '%.2f A', access='input'),

            # Energy: Wh -> kWh (divide by 1000)
            Reg_s64b(30000, '/Ac/Energy/Forward', 1000, '%.3f kWh', access='input'),
            #Reg_s64b(30004, '/Session/Energy', 1000, '%.3f kWh', access='input'),

            # Status :contentReference[oaicite:23]{index=23}
            PeblarCpStatusReg(30110, '/Status', access='input'),
            PeblarModeReg(30110, '/Mode', access='input'),
            #Reg_u16(30110, '/Test', access='input'),

            # Actual communicated current to EV: mA uint32 -> A :contentReference[oaicite:24]{index=24}
            # Reg_u32b(30113, '/Current', 1000, '%.2f A', access='input'),

            # Control paths (Holding) :contentReference[oaicite:25]{index=25}
            #start_stop,
            #set_current,
            #max_current,
            Reg_u32b(40000, '/SetCurrent', 1000, '%d A', write=(0, 16), access='holding'),
            PeblarMaxCurentReg(40000, '/MaxCurrent', 1000, '%.1f A', access='holding'),

            #Reg_u32b(40000, '/MaxCurrent', 1000, '%.1f A', write=(0, 32), access='holding'),
            PeblarStartStopReg(40000, '/StartStop', scale=1000, text='%d', write=(0, 16), access='holding'),

            # Optional Peblar extras
            # Reg_u16(40002, '/Force1Phase', write=(0, 1), access='holding'),
            # Reg_u32b(40050, '/AliveTimeout', 1, '%d s', write=(0, 86400), access='holding'),
            # Reg_s32b(40052, '/FallbackCurrent', 1000, '%.1f A', write=(0, 32), access='holding'),
        ]

        # Attach callable write handler for StartStop
        def _startstop_write(val):
            return start_stop._write_startstop(self, val)

        start_stop.write = _startstop_write

        #self.dbus.add_path('/MaxCurrent', 16)
        # Nice-to-have: aliases so other parts of Venus UI still show total power under both paths
        #self.alias_regs = {
        #    '/Ac/Power': ('/Ac/Power',),
        #}

    def get_ident(self):
        # Stable id based on serial
        serial = self.info.get('/Serial')
        if serial:
            return f'peblar_{serial}'
        return 'peblar_unknown'


# --- Probe registration ---
# Use ModbusApiVersionMajor as “model register”: document states major version 1. :contentReference[oaicite:26]{index=26}
models = {
    1: {'model': 'Peblar Modbus API v1', 'handler': PeblarEVCharger},
}

probe.add_handler(
    probe.ModelRegister(
        Reg_u16(30123, access='input'),  # ModbusApiVersionMajor :contentReference[oaicite:27]{index=27}
        models,
        methods=['tcp'],
        units=[1],
    )
)
