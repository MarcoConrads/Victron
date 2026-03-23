from __future__ import annotations

import time
from enum import IntEnum

import device
import probe
from register import Reg_text, Reg_u16, Reg_u32b, Reg_s16


class INV_STATUS(IntEnum):
    OFF = 0
    RUNNING = 7
    FAULT = 10


class GrowattStatusReg(Reg_u16):
    """
    Growatt input register 0:
      0 = waiting
      1 = normal
      3 = fault
    Map to generic Victron-style status values.
    """

    def decode(self, values):
        if not values or values[0] is None:
            return False

        raw = int(values[0]) & 0xFFFF
        if raw == 1:
            self.value = int(INV_STATUS.RUNNING)
        elif raw == 3:
            self.value = int(INV_STATUS.FAULT)
        else:
            self.value = int(INV_STATUS.OFF)

        self.valid = True
        return True


class GrowattPowerLimitReg(Reg_u16):
    """
    Virtualized export/output power limit in percent.

    Underlying registers:
      HR 122 = ExportLimit_En/dis
        0 disable limit
        1 enable 485 export limit
      HR 123 = ExportLimitPowerRate in 0.1%

    D-Bus value exposed here is integer percent 0..100.
    100 means unlimited (register 122 = 0).
    0..99 means limit enabled and register 123 set accordingly.
    """

    def __init__(self, base, name, device_obj, access='holding'):
        super().__init__(base, name, access=access)
        self.device_obj = device_obj
        self._cached_pct = 100

    def decode(self, values):
        if not values or values[0] is None:
            return False

        raw = int(values[0]) & 0xFFFF
        pct = max(0, min(100, int(round(raw / 10.0))))

        try:
            enabled = self.device_obj.read_register(self.device_obj._export_limit_enable)
            enabled_val = int(self.device_obj._export_limit_enable.value or 0)
        except Exception:
            enabled_val = 0

        if enabled_val == 0:
            pct = 100

        self._cached_pct = pct
        self.value = pct
        self.valid = True
        return True

    def _write_limit(self, val):
        return self.device_obj._apply_power_limit(val)


class GrowattMOD10KTL3X(device.ModbusDevice):
    vendor_id = 'growatt'
    vendor_name = 'Growatt'
    device_type = 'PV inverter'

    allowed_roles = None
    default_role = 'pvinverter'
    default_instance = 40
    default_access = 'input'

    productid = 0xA14A
    productname = 'Growatt MOD 10KTL3-X'
    model = 'MOD 10KTL3-X (Modbus)'

    min_timeout = 1.0

    def device_init(self):
        self._last_limit_apply = 0

        # Writable holding registers for export/output limit.
        self._export_limit_enable = Reg_u16(122, '/Control/ExportLimitEnable', access='holding')
        self._export_limit_rate = GrowattPowerLimitReg(123, '/Ac/PowerLimit', self, access='holding')
        self._remote_ctrl_en = Reg_u16(108, '/Control/RemoteCtrlEn', access='input')
        self._remote_ctrl_power = Reg_u16(109, '/Control/RemoteCtrlPower', access='input')

        # TL3-X family supports holding range 0..124 and 125..249.
        # New serial number is at 209..223 (30 ASCII chars).
        self.info_regs = [
            Reg_text(209, 15, '/Serial', encoding='ascii', access='holding'),
            Reg_text(23, 5, '/SerialShort', encoding='ascii', access='holding'),
            Reg_u16(22, '/BaudrateCode', access='holding'),
            Reg_u16(30, '/ModbusAddress', access='holding'),
            Reg_u16(43, '/DeviceTypeCode', access='holding'),
        ]

        self.data_regs = [
            GrowattStatusReg(0, '/Status', access='input'),

            Reg_u32b(1, '/Pv/Power', 10, '%.1f W', access='input'),

            Reg_u16(3, '/Pv/0/V', 10, '%.1f V', access='input'),
            Reg_u16(4, '/Pv/0/I', 10, '%.1f A', access='input'),
            Reg_u32b(5, '/Pv/0/P', 10, '%.1f W', access='input'),

            Reg_u16(7, '/Pv/1/V', 10, '%.1f V', access='input'),
            Reg_u16(8, '/Pv/1/I', 10, '%.1f A', access='input'),
            Reg_u32b(9, '/Pv/1/P', 10, '%.1f W', access='input'),

            Reg_u32b(35, '/Ac/Power', 10, '%.1f W', access='input'),
            Reg_u16(37, '/Ac/Frequency', 100, '%.2f Hz', access='input'),

            Reg_u16(38, '/Ac/L1/Voltage', 10, '%.1f V', access='input'),
            Reg_u16(39, '/Ac/L1/Current', 10, '%.1f A', access='input'),
            Reg_u32b(40, '/Ac/L1/Power', 10, '%.1f VA', access='input'),

            Reg_u16(42, '/Ac/L2/Voltage', 10, '%.1f V', access='input'),
            Reg_u16(43, '/Ac/L2/Current', 10, '%.1f A', access='input'),
            Reg_u32b(44, '/Ac/L2/Power', 10, '%.1f VA', access='input'),

            Reg_u16(46, '/Ac/L3/Voltage', 10, '%.1f V', access='input'),
            Reg_u16(47, '/Ac/L3/Current', 10, '%.1f A', access='input'),
            Reg_u32b(48, '/Ac/L3/Power', 10, '%.1f VA', access='input'),

            Reg_u16(50, '/Ac/L1L2/Voltage', 10, '%.1f V', access='input'),
            Reg_u16(51, '/Ac/L2L3/Voltage', 10, '%.1f V', access='input'),
            Reg_u16(52, '/Ac/L3L1/Voltage', 10, '%.1f V', access='input'),

            Reg_u32b(53, '/Yield/User', 10, '%.1f kWh', access='input'),
            Reg_u32b(55, '/Yield/System', 10, '%.1f kWh', access='input'),
            Reg_u32b(57, '/WorkTime', 2, '%.0f s', access='input'),

            Reg_u32b(59, '/Pv/0/Yield/Today', 10, '%.1f kWh', access='input'),
            Reg_u32b(61, '/Pv/0/Yield/Total', 10, '%.1f kWh', access='input'),
            Reg_u32b(63, '/Pv/1/Yield/Today', 10, '%.1f kWh', access='input'),
            Reg_u32b(65, '/Pv/1/Yield/Total', 10, '%.1f kWh', access='input'),
            Reg_u32b(91, '/Pv/Yield/Total', 10, '%.1f kWh', access='input'),

            Reg_s16(93, '/Temperature', 10, '%.1f C', access='input'),
            Reg_s16(94, '/Temperature/IPM', 10, '%.1f C', access='input'),
            Reg_s16(95, '/Temperature/Boost', 10, '%.1f C', access='input'),

            Reg_u16(100, '/Ac/PowerFactor', 10000, '%.4f', access='input'),
            Reg_u16(101, '/Ac/PowerPercent', 1, '%d %%', access='input'),
            Reg_u32b(102, '/Ac/MaxPower', 10, '%.1f W', access='input'),
            Reg_u16(104, '/DeratingMode', access='input'),
            Reg_u16(105, '/ErrorCode', access='input'),
            Reg_u16(107, '/ErrorSubCode', access='input'),
            self._remote_ctrl_en,
            self._remote_ctrl_power,
            Reg_u16(110, '/WarningBit', access='input'),
            Reg_u16(111, '/WarningSubCode', access='input'),
            Reg_u16(112, '/WarningCode', access='input'),

            self._export_limit_enable,
            self._export_limit_rate,
        ]

        self._export_limit_rate.write = self._handle_power_limit_write

    def init_settings(self):
        settings_path = '/Settings/GrowattMod10Ktl3X'
        settings = {
            'powerlimit_pct': [settings_path + '/PowerLimitPct', 100, 0, 100],
        }
        self.settings.addSettings(settings)

    def init_dbus(self):
        super().init_dbus()
        self.init_settings()

        self.dbus.add_path(
            '/Ac/PowerLimit',
            int(self.settings['powerlimit_pct']),
            writeable=True,
            onchangecallback=self._handle_power_limit_change,
        )
        self.dbus.add_path('/Ac/PowerLimitInfo', '100=unlimited, <100 enables export limit', writeable=False)
        self.dbus.add_path('/Connected', 1, writeable=False)
        self.dbus.add_path('/DeviceType', 'Inverter', writeable=False)

        try:
            self._apply_power_limit(int(self.settings['powerlimit_pct']))
        except Exception:
            pass

    def _handle_power_limit_change(self, path, value):
        try:
            pct = int(value)
        except Exception:
            return False

        if pct < 0 or pct > 100:
            return False

        if not self._apply_power_limit(pct):
            return False

        self.settings['powerlimit_pct'] = pct
        return True

    def _handle_power_limit_write(self, value):
        try:
            pct = int(value)
        except Exception:
            return False

        if pct < 0 or pct > 100:
            return False

        if not self._apply_power_limit(pct):
            return False

        self.settings['powerlimit_pct'] = pct
        try:
            self.dbus['/Ac/PowerLimit'] = pct
        except Exception:
            pass
        return True

    def _apply_power_limit(self, pct):
        try:
            pct = int(pct)
        except Exception:
            return False

        pct = max(0, min(100, pct))

        # Avoid hammering RS485/TCP stack.
        now = time.time()
        if now - self._last_limit_apply < 0.2:
            time.sleep(0.2)
        self._last_limit_apply = time.time()

        try:
            if pct >= 100:
                # Unlimited output / export limit disabled.
                self.write_register(self._export_limit_enable, 0)
                # Keep register 123 at 100.0% for readability.
                self.write_register(self._export_limit_rate, 1000)
            else:
                # Enable 485 export limit and set percentage in 0.1% units.
                self.write_register(self._export_limit_rate, pct * 10)
                self.write_register(self._export_limit_enable, 1)

            try:
                self._export_limit_rate.value = pct
                self._export_limit_enable.value = 0 if pct >= 100 else 1
            except Exception:
                pass

            return True
        except Exception as e:
            print('failed to apply Growatt power limit:', e)
            return False

    def get_ident(self):
        reg = self.info_regs[0]
        self.read_register(reg)

        serial = (reg.value or '').strip().replace('-', '_').replace(' ', '_')
        if serial:
            return f'growatt_mod10ktl3x_{serial}'
        return 'growatt_mod10ktl3x_unknown'


models = {
    1: {'model': 'Growatt MOD 10KTL3-X', 'handler': GrowattMOD10KTL3X},
}

probe.add_handler(
    probe.ModelRegister(
        Reg_u16(0, access='input'),
        models,
        methods=['tcp', 'rtu'],
        units=[1],
    )
)
