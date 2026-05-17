from pymodbus.client.sync import ModbusTcpClient

HOST = "192.168.11.68"
PORT = 502
UNIT_ID = 2

def read_input_registers(start, count):
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


c = ModbusTcpClient(HOST, port=502, timeout=3)

print("connect:", c.connect())

rr = c.read_input_registers(0, 125, unit=2)
print("input", rr)
print(rr.registers)

c.close()

registers = read_input_registers(0, 125)
print (registers)
