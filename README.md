# Growatt, Ecoforest and Peblar on Venus OS

The three drivers share `base_modbus_dbus.py`, `modbus_codec.py` and
`modbus_types.py`. They run as separate services from a single directory:
`/data/dbus-modbus-drivers`.

## Installing on the Cerbo

1. Copy all `.py` files from this directory and `start-services.sh` to
   `/data/dbus-modbus-drivers` on the Cerbo.
2. Check the `HOST`, `PORT`, `UNIT_ID`, `DEVICE_INSTANCE` and `POLL_INTERVAL_MS`
   settings in each `*_dbus_config.py` file. The installer displays the
   configured addresses; it cannot determine your devices' addresses for you.
3. Stop any old or manually started instances of these drivers. If you use
   the old Peblar integration, also remove its import from `dbus-modbus-client`,
   as described in `peblar_ev_charger_driver.md` in the repository root.
4. Run the following commands as root over SSH:

```sh
cd /data/dbus-modbus-drivers
python3 install_drivers.py --check
python3 install_drivers.py
```

The installer checks the Python dependencies: DBus, GLib,
`pymodbus.client.sync` (pymodbus 2.x), `settingsdevice` and `vedbus`.
Missing dependencies are reported before installation begins.
No packages are downloaded or updated automatically.

The installer creates the `dbus-growatt`, `dbus-ecoforest` and `dbus-peblar`
services and starts them immediately. Existing configuration files are
preserved. Existing services with the same names that belong to another
installation are not overwritten. Stop and relocate any such service first.

The service files remain under `/data`. A managed block in `/data/rc.local`
restores the links in `/service` at startup, including after a firmware update.
Existing startup commands are preserved; the original `rc.local` is backed up
once as `/data/rc.local.before-modbus-drivers`. If necessary, the root
filesystem is remounted as writable to restore the service links.

Code and configuration survive firmware updates, but you may need to reinstall
any Python dependencies you installed yourself.

## Checking and debugging

```sh
svstat /service/dbus-growatt /service/dbus-ecoforest /service/dbus-peblar
tail -f /var/log/dbus-growatt/current
```

For the other logs, use `dbus-ecoforest` or `dbus-peblar`.
Logs are rotated at approximately 256 KiB per file, keeping up to three old
files per driver. The logs under `/var/log` are not intended as a persistent
archive across reboots. A running process does not prove that Modbus
communication is working: also check the log and the measurements on D-Bus.

For a manual test or VS Code debugging session:

```sh
svc -d /service/dbus-growatt
python3 /data/dbus-modbus-drivers/growatt_dbus.py
```

Stop the test with Ctrl+C and restart the service with:

```sh
svc -u /service/dbus-growatt
```

`svc -d` stops the service for the current session; the startup hook enables
all three drivers again at the next reboot.

## Updating

To update, upload the files to a separate directory under `/data` first,
then run `python3 install_drivers.py` from that directory. The installer stops
its own services during the update and preserves the existing configuration
in the destination directory. If you upload directly to the destination,
take care not to overwrite your configuration files or modify running code
during the upload.

Venus OS startup mechanism:
https://github.com/victronenergy/venus/wiki/howto-add-a-driver-to-Venus
