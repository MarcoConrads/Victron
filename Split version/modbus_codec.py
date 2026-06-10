import logging

# Generic Modbus value conversion helpers.

class ModbusValueCodec:
    """Generic Modbus value conversion helpers."""

    @staticmethod
    def u16(registers, index=0):
        """Read one 16-bit register as unsigned integer."""
        return int(registers[index]) & 0xFFFF

    @staticmethod
    def i16(registers, index=0):
        """Read one 16-bit register as signed integer."""
        value = ModbusValueCodec.u16(registers, index)
        if value >= 0x8000:
            value -= 0x10000
        return value

    @staticmethod
    def u32(registers, index=0):
        """Combine one or two 16-bit registers into unsigned integer."""
        if index + 1 >= len(registers):
            return ModbusValueCodec.u16(registers, index)
        return (ModbusValueCodec.u16(registers, index) << 16) + ModbusValueCodec.u16(registers, index + 1)

    @staticmethod
    def s32(registers, index=0):
        """Combine two 16-bit registers into signed 32-bit."""
        value = ModbusValueCodec.u32(registers, index)
        if value >= 0x80000000:
            value -= 0x100000000
        return value

    @staticmethod
    def sum_u16(registers):
        """Sum multiple unsigned 16-bit register values."""
        return sum(ModbusValueCodec.u16(registers, index) for index in range(len(registers)))

    @staticmethod
    def sum_i16(registers):
        """Sum multiple signed 16-bit register values."""
        return sum(ModbusValueCodec.i16(registers, index) for index in range(len(registers)))

    @staticmethod
    def decode_ascii_registers(registers, start, count):
        """
        Decode Modbus registers containing ASCII characters.
        Each 16-bit register contains two ASCII bytes.
        """
        result = ""

        for i in range(start, start + count):
            value = ModbusValueCodec.u16(registers, i)
            high = (value >> 8) & 0xFF
            low = value & 0xFF

            if high != 0:
                result += chr(high)

            if low != 0:
                result += chr(low)

        return result.strip()

    @classmethod
    def decode(cls, reg, values):
        """Decode one REG item from the values dictionary."""
        start = reg["address"]
        length = reg["length"]
        encoding = reg.get("encoding")

        raw_values = [values[start + offset] for offset in range(length)]

        if encoding == "bool":
            value = bool(raw_values[0])
        elif encoding == "i16":
            value = cls.i16(raw_values, 0)
        elif encoding == "u16":
            value = cls.u16(raw_values, 0)
        elif encoding == "sum_i16":
            value = cls.sum_i16(raw_values)
        elif encoding == "sum_u16":
            value = cls.sum_u16(raw_values)
        elif encoding == "ascii":
            value = cls.decode_ascii_registers(raw_values, 0, length)
        elif encoding == "s32":
            value = cls.s32(raw_values, 0)
        elif encoding == "u32":
            value = cls.u32(raw_values, 0)
        elif encoding == "string":
            value = str(raw_values[0]) if raw_values else ""
        else:
            raise ValueError(f"Unsupported encoding {encoding}")

        if "map" in reg:
            value = reg["map"].get(value, reg["default"])

        if "scale" in reg and reg["scale"]:
            value = value / reg["scale"]

        return value


# Backwards-compatible function names.
def u16(registers, index=0):
    return ModbusValueCodec.u16(registers, index)


def i16(registers, index=0):
    return ModbusValueCodec.i16(registers, index)


def u32(registers, index=0):
    return ModbusValueCodec.u32(registers, index)


def s32(registers, index=0):
    return ModbusValueCodec.s32(registers, index)


def sum_u16(registers):
    return ModbusValueCodec.sum_u16(registers)


def sum_i16(registers):
    return ModbusValueCodec.sum_i16(registers)


def decode_ascii_registers(registers, start, count):
    return ModbusValueCodec.decode_ascii_registers(registers, start, count)


def decode_value(reg, values):
    return ModbusValueCodec.decode(reg, values)


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
