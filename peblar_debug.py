from pymodbus.client.sync import ModbusTcpClient

HOST = "192.168.11.66"
PORT = 502
UNIT = 1

client = ModbusTcpClient(HOST, port=PORT)

def read_input(addr, count):
    return client.read_input_registers(addr - 30001, count, unit=UNIT)

def read_holding(addr, count):
    return client.read_holding_registers(addr - 40001, count, unit=UNIT)

def regs_to_string(regs):
    data = bytearray()
    for r in regs:
        data.append((r >> 8) & 0xFF)
        data.append(r & 0xFF)
    return data.decode("utf-8", errors="ignore").strip("\x00 ").strip()

def read_int32(regs):
    return (regs[0] << 16) | regs[1]

def read_int64(regs):
    return (
        (regs[0] << 48)
        | (regs[1] << 32)
        | (regs[2] << 16)
        | regs[3]
    )

print("Connecting to Peblar:", HOST)

if not client.connect():
    print("Connection failed")
    exit(1)

print()

# ProductPn
r = read_input(30062, 12)
if not r.isError():
    print("ProductPn:", regs_to_string(r.registers))

# Firmware
r = read_input(30074, 12)
if not r.isError():
    print("Firmware:", regs_to_string(r.registers))

# API version
r = read_input(30123, 1)
if not r.isError():
    print("Modbus API Version:", r.registers[0])

print()

# Power total
r = read_input(30014, 2)
if not r.isError():
    print("PowerTotal:", read_int32(r.registers), "W")

# Voltage
r = read_input(30016, 2)
if not r.isError():
    print("Voltage L1:", read_int32(r.registers), "V")

r = read_input(30018, 2)
if not r.isError():
    print("Voltage L2:", read_int32(r.registers), "V")

r = read_input(30020, 2)
if not r.isError():
    print("Voltage L3:", read_int32(r.registers), "V")

print()

# Current (mA → A)
r = read_input(30022, 2)
if not r.isError():
    print("Current L1:", read_int32(r.registers) / 1000, "A")

r = read_input(30024, 2)
if not r.isError():
    print("Current L2:", read_int32(r.registers) / 1000, "A")

r = read_input(30026, 2)
if not r.isError():
    print("Current L3:", read_int32(r.registers) / 1000, "A")

print()

# CP State
r = read_input(30110, 1)
if not r.isError():
    cp = chr(r.registers[0])
    print("CP State:", cp)

print()

# Charge current limit
r = read_holding(40000, 2)
if not r.isError():
    print("ChargeCurrentLimit:", read_int32(r.registers) / 1000, "A")

client.close()
