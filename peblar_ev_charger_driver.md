# Peblar EV Charger for Victron Venus OS

Peblar uses the same standalone structure as the split Growatt and Ecoforest
services, with `BaseModbusDbus` for DBus, persistent settings and Modbus polling.

- `Split version/peblar_dbus.py`: service, start/stop, current control and session timer.
- `Split version/peblar_dbus_config.py`: host, port, unit ID, instance and polling interval.
- `Split version/peblar_dbus_registers.py`: register definitions and persistent settings.
- `Split version/base_modbus_dbus.py`, `modbus_codec.py`, `modbus_types.py`: shared modules.
- `peblar_ev_charger.py`: optional launcher from the repository root.

## Installation

Configure `HOST` in `peblar_dbus_config.py` (default `192.168.11.66`), port 502,
unit 1 and device instance 40. Copy the three Peblar modules and three shared
modules into one directory, for example `/data/dbus-peblar`, then run:

```sh
python3 /data/dbus-peblar/peblar_dbus.py
```

The service requires the same Python dependencies as the other split drivers:
`pymodbus.client.sync`, DBus, GLib, `settingsdevice` and `vedbus` from
`velib_python`. The launcher also works when the repository layout is preserved:
`python3 peblar_ev_charger.py`.

For supervised startup, create a Venus OS runit service whose `run` script
executes `exec python3 /data/dbus-peblar/peblar_dbus.py` (with a shell shebang).
Disable the previous Peblar handler in `dbus-modbus-client` before starting this
service, by removing its `import peblar_ev_charger` and restarting that service.
The old `install_peblar_driver.sh` is retired and exits without making changes.

## DBus and controls

The service name is `com.victronenergy.evcharger.peblar_40` (instance configurable).
It no longer registers a probe handler in `dbus-modbus-client` or uses a serial
number in the service name. `/Serial`, `/ProductPn`, `/FirmwareVersion`,
`/PhaseCount` and `/Ac/NumberOfPhases` remain available.

Measurements retain their original addresses, units and paths:

| Registers | DBus paths | Encoding / unit |
| --- | --- | --- |
| 30000 / 30004 | `/Ac/Energy/Forward`, `/Session/Energy` | Signed 64-bit, Wh to kWh |
| 30008 / 30010 / 30012 / 30014 | `/Ac/L1/Power` through `/Ac/L3/Power`, `/Ac/Power` | Signed 32-bit, W |
| 30016 / 30018 / 30020 | `/Ac/L1/Voltage` through `/Ac/L3/Voltage` | Signed 32-bit, V |
| 30022 / 30024 / 30026 | `/Ac/L1/Current` through `/Ac/L3/Current` | Signed 32-bit, mA to A |
| 30110 | `/Status` | A=0, B=1, C/D=2, E/F/I=15, other=1 |
| 40000 | `/SetCurrent`, `/StartStop` | Two holding registers, unsigned 32-bit mA |

`/Current` mirrors L1 current, as in the original driver. `/SetCurrent` accepts
0 (stop), or 6 A through `/MaxCurrent`. `/StartStop` accepts 0 or 1; start restores
the most recent nonzero current, bounded by `/MaxCurrent`, or defaults to 6 A.
Both control paths update only after a successful Modbus write.

Settings retain their existing paths under `/Settings/Peblar`: `Position` (0-1),
`Mode` (0-2) and `MaxCurrent` (6-32 A, default 16). Mode is a stored UI setting;
automatic and scheduled charging logic is not implemented. `/CustomName` is
stored under `/Settings/Devices/Peblar40/CustomName` with the configured instance.

`/Session/Time` counts seconds while L1 current exceeds 0.1 A, and resets when
charging stops or communication fails. `/Connected` indicates polling success.
Register values remain at their last known values on communication errors.
