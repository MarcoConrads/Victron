from pymodbus.client.sync import ModbusTcpClient

# Peblar IP adres
HOST = "192.168.11.66"
PORT = 502
UNIT_ID = 1

# ProductPn register
REGISTER = 30062
REGISTER_COUNT = 12  # 24 bytes string = 12 registers

client = ModbusTcpClient(HOST, port=PORT)

if not client.connect():
    print("Connection failed")
    exit(1)

result = client.read_input_registers(REGISTER, REGISTER_COUNT, unit=UNIT_ID)

if result.isError():
    print("Modbus read error:", result)
else:
    regs = result.registers

    # registers → bytes
    data = bytearray()
    for r in regs:
        data.append((r >> 8) & 0xFF)
        data.append(r & 0xFF)

    product = data.decode("utf-8", errors="ignore").strip("\x00 ").strip()

    print("ProductPn:", product)

client.close()
