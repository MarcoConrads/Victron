from pymodbus.client.sync import ModbusTcpClient

HOST = "192.168.11.66"   # pas aan
PORT = 502
UNIT_ID = 1

# Registers
PRODUCT_REGISTER = 30062
PRODUCT_COUNT = 12        # string24 = 12 registers

API_VERSION_REGISTER = 30123
API_VERSION_COUNT = 1

# Modbus input registers beginnen bij 30001 → offset berekenen
PRODUCT_ADDRESS = PRODUCT_REGISTER
API_ADDRESS = API_VERSION_REGISTER


def registers_to_string(registers):
    data = bytearray()
    for reg in registers:
        data.append((reg >> 8) & 0xFF)
        data.append(reg & 0xFF)
    return data.decode("utf-8", errors="ignore").strip("\x00 ").strip()


def main():
    client = ModbusTcpClient(HOST, port=PORT)

    if not client.connect():
        print("Connection failed")
        return

    try:
        # ---- ProductPn ----
        result = client.read_input_registers(PRODUCT_ADDRESS, PRODUCT_COUNT, unit=UNIT_ID)

        if result.isError():
            print("Error reading ProductPn:", result)
        else:
            product = registers_to_string(result.registers)
            print("ProductPn:", product)

        # ---- API Version ----
        result = client.read_input_registers(API_ADDRESS, API_VERSION_COUNT, unit=UNIT_ID)

        if result.isError():
            print("Error reading ModbusApiVersionMajor:", result)
        else:
            api_version = result.registers[0]
            print("ModbusApiVersionMajor:", api_version)

    finally:
        client.close()


if __name__ == "__main__":
    main()
