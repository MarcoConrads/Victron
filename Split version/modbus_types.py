# Generic Modbus type and error-policy constants.

# Modbus data types / function groups
MB_COIL = "coil"
MB_INPUT_BINARY = "input_binary"
MB_INPUT_REGISTER = "input_register"
MB_HOLDING_REGISTER = "holding_register"
MB_NONE = None

REGISTER_TYPES = (MB_INPUT_REGISTER, MB_HOLDING_REGISTER)
BINARY_TYPES = (MB_COIL, MB_INPUT_BINARY)
MODBUS_TYPES = (MB_COIL, MB_INPUT_BINARY, MB_INPUT_REGISTER, MB_HOLDING_REGISTER)

# Behaviour on Modbus read error.
ON_ERROR_DEFAULT = "default"
ON_ERROR_KEEP = "keep"

MAX_REGISTERS_PER_READ = 125
MAX_BITS_PER_READ = 100
