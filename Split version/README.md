# DBus Growatt split version

Start the service with:

```bash
python3 dbus_growatt.py
```

Files:

- `dbus_growatt.py`: entrypoint / GLib loop.
- `config.py`: host, unit id, device instance and polling settings.
- `modbus_types.py`: Modbus type constants and read limits.
- `modbus_codec.py`: generic conversions: `bool`, `i16`, `u16`, `sum_i16`, `sum_u16`, `s32`, `u32`, `ascii`, `string`.
- `base_modbus_dbus.py`: generic DBus, SettingsDevice, Modbus read plan, read/decode/write handling.
- `growatt_registers.py`: Growatt register map.
- `growatt_dbus.py`: Growatt-specific derived values and writable power limit.
