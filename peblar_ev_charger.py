from __future__ import annotations

from enum import IntEnum
import time

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

class EVC_POSITION(IntEnum):
    OUTPUT = 0
    INPUT = 1

class EVC_ADJ_POSITION(IntEnum):
    FIXED = 0
    ADJUSTABLE = 1

class EVC_AUTO_START(IntEnum):
    DISABLED = 0
    ENABLED = 1

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


class PeblarCpStatusReg(Reg_u16):
    '''
    Peblar CpState is documented as a 'char' stored in uint16, values A/B/C/D/E/F/I/U.
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

        if c == 'A':
            self.value = int(EVC_STATUS.DISCONNECTED)
        elif c == 'B':
            self.value = int(EVC_STATUS.CONNECTED)
        elif c in ('C', 'D'):
            self.value = int(EVC_STATUS.CHARGING)
        elif c in ('E', 'F', 'I'):
            self.value = int(EVC_STATUS.FAULT)
        else:
            self.value = int(EVC_STATUS.CONNECTED)

        self.valid = True
        return True


class PeblarCurrentReg(Reg_s32b):
    """
    Current register that also updates /Session/Time.
    Peblar current registers are mA, exposed as A via scale=1000.
    """
    def __init__(self, base, name, scale, text, charger, access='input'):
        super().__init__(base, name, scale, text, access=access)
        self.charger = charger

    def decode(self, values):
        ok = super().decode(values)
        if not ok or self.value is None:
            return ok

        try:
            current_a = float(self.value)
        except Exception:
            current_a = 0.0

        self.charger._update_session_time(current_a > 0.1)
        return True


class PeblarStartStopReg(Reg_u32b):
    '''
    Expose /StartStop as 0/1 on D-Bus, while underlying control is ChargeCurrentLimit (mA) at register 40000.
    - read: if limit > 0 => ENABLED else DISABLED
    - write: 0 => write 0mA ; 1 => restore last set current (or 6A default)
    '''
    def __init__(self, base, name, scale=1000, text=None, write=None, access=None):
        super().__init__(base, name, scale=scale, text=text, write=write, access=access)
        self._last_nonzero_ma = 6000

    def decode(self, values):
        ok = super().decode(values)
        if not ok or self.value is None:
            return ok

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
            device_obj.write_register(self, 0)
            return True

        if v == int(EVC_CHARGE.ENABLED):
            restore_ma = max(6000, int(self._last_nonzero_ma))
            restore_a = restore_ma / 1000.0
            device_obj.write_register(self, restore_a)
            return True

        return False


class PeblarEVCharger(device.ModbusDevice):
    '''
    Peblar Modbus TCP server (port 502) with big-endian words/bytes.
    '''

    vendor_id = 'peblar'
    vendor_name = 'Peblar'
    device_type = 'EV charger'

    allowed_roles = None
    default_role = 'evcharger'
    default_instance = 40
    default_access = 'input'

    productid = 0xB0B1
    productname = 'Peblar EV Charger'
    model = 'Peblar (Modbus TCP)'

    min_timeout = 0.5

    def device_init(self):
        self._session_start = None
        self._session_time = 0

        self.info_regs = [
            Reg_text(30050, 12, '/Serial', encoding='utf-8', access='input'),
            Reg_text(30062, 12, '/ProductPn', encoding='utf-8', access='input'),
            Reg_text(30074, 12, '/FirmwareVersion', encoding='utf-8', access='input'),
            Reg_u16(30092, '/PhaseCount', access='input'),
        ]

        set_current = Reg_u32b(40000, '/SetCurrent', 1000, '%.1f A', write=True, access='holding')
        start_stop = PeblarStartStopReg(40000, '/StartStop', scale=1000, text='%d', access='holding')

        self.data_regs = [
            Reg_s32b(30008, '/Ac/L1/Power', 1, '%d W', access='input'),
            Reg_s32b(30010, '/Ac/L2/Power', 1, '%d W', access='input'),
            Reg_s32b(30012, '/Ac/L3/Power', 1, '%d W', access='input'),
            Reg_s32b(30014, '/Ac/Power', 1, '%d W', access='input'),

            Reg_s32b(30016, '/Ac/L1/Voltage', 1, '%d V', access='input'),
            Reg_s32b(30018, '/Ac/L2/Voltage', 1, '%d V', access='input'),
            Reg_s32b(30020, '/Ac/L3/Voltage', 1, '%d V', access='input'),

            PeblarCurrentReg(30022, '/Current', 1000, '%.2f A', self, access='input'),
            Reg_s32b(30022, '/Ac/L1/Current', 1000, '%.2f A', access='input'),
            Reg_s32b(30024, '/Ac/L2/Current', 1000, '%.2f A', access='input'),
            Reg_s32b(30026, '/Ac/L3/Current', 1000, '%.2f A', access='input'),

            Reg_s64b(30000, '/Ac/Energy/Forward', 1000, '%.3f kWh', access='input'),
            Reg_s64b(30004, '/Session/Energy', 1000, '%.3f kWh', access='input'),

            PeblarCpStatusReg(30110, '/Status', access='input'),

            start_stop,
            set_current,
        ]

        def _startstop_write(val):
            return start_stop._write_startstop(self, val)

        start_stop.write = _startstop_write

    def _update_session_time(self, charging):
        now = time.time()

        if charging:
            if self._session_start is None:
                self._session_start = now
            self._session_time = int(now - self._session_start)
        else:
            self._session_start = None
            self._session_time = 0

        if hasattr(self, 'dbus') and self.dbus is not None:
            try:
                self.dbus['/Session/Time'] = self._session_time
            except Exception:
                pass

    def init_dbus(self):
        super().init_dbus()
        self.dbus.add_path('/Mode', EVC_MODE.MANUAL, writeable=False)
        self.dbus.add_path('/MaxCurrent', 16, writeable=False)
        self.dbus.add_path('/Position', EVC_POSITION.OUTPUT, writeable=False)
        self.dbus.add_path('/PositionIsAdjustable', EVC_ADJ_POSITION.FIXED, writeable=False)
        self.dbus.add_path('/AutoStart', EVC_AUTO_START.ENABLED, writeable=False)
        self.dbus.add_path('/Session/Time', 0, writeable=False)

    def get_ident(self):
        reg = self.info_regs[0]
        self.read_register(reg)
        serial = reg.value
        serial = serial.replace('-', '_')
        if serial:
            return f'peblar_{serial}'
        return 'peblar_unknown'


models = {
    1: {'model': 'Peblar Modbus API v1', 'handler': PeblarEVCharger},
}

probe.add_handler(
    probe.ModelRegister(
        Reg_u16(30123, access='input'),
        models,
        methods=['tcp'],
        units=[1],
    )
)
