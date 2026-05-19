#!/usr/bin/env python3
# dbus_growatt_settingsdevice_unique_v2.py

import sys
import logging
from gi.repository import GLib
import dbus.mainloop.glib

sys.path.insert(0, "/opt/victronenergy/dbus-systemcalc-py/ext/velib_python")
sys.path.insert(0, "/data/velib_python")

from vedbus import VeDbusService
from settingsdevice import SettingsDevice

HOST = "192.168.11.68"
PORT = 502
UNIT_ID = 2

DEVICE_INSTANCE = 48
POSITION = 1

MB_NONE = None
ON_ERROR_KEEP = "keep"

REG = [
    {
        "name": "process_name",
        "path": "/Mgmt/ProcessName",
        "address": None,
        "length": 0,
        "regtype": MB_NONE,
        "encoding": "string",
        "default": __file__,
        "on_error": ON_ERROR_KEEP,
    },
    {
        "name": "process_version",
        "path": "/Mgmt/ProcessVersion",
        "address": None,
        "length": 0,
        "regtype": MB_NONE,
        "encoding": "string",
        "default": "1.1",
        "on_error": ON_ERROR_KEEP,
    },
    {
        "name": "connection",
        "path": "/Mgmt/Connection",
        "address": None,
        "length": 0,
        "regtype": MB_NONE,
        "encoding": "string",
        "default": f"Modbus TCP {HOST}:{PORT}, unit {UNIT_ID}",
        "on_error": ON_ERROR_KEEP,
    },
    {
        "name": "deviceinstance",
        "path": "/DeviceInstance",
        "address": None,
        "length": 0,
        "regtype": MB_NONE,
        "encoding": "u32",
        "default": DEVICE_INSTANCE,
        "on_error": ON_ERROR_KEEP,
    },
    {
        "name": "custom_name",
        "path": "/CustomName",
        "address": None,
        "length": 0,
        "regtype": MB_NONE,
        "encoding": "string",
        "default": "Growatt",
        "on_error": ON_ERROR_KEEP,
        "writeable": True,
    },
    {
        "name": "position",
        "path": "/Position",
        "address": None,
        "length": 0,
        "regtype": MB_NONE,
        "encoding": "u32",
        "default": POSITION,
        "on_error": ON_ERROR_KEEP,
        "writeable": True,
    },
]

class GrowattDbus:
    def __init__(self):
        self.service = VeDbusService(
            f"com.victronenergy.pvinverter.growatt_{DEVICE_INSTANCE}",
            register=False,
        )

        self.settings = SettingsDevice(
            bus=None,
            supportedSettings={
                'customname': [
                    f'/Settings/Devices/Growatt_{DEVICE_INSTANCE}/CustomName',
                    'Growatt',
                    0,
                    0,
                ],
                'position': [
                    f'/Settings/Devices/Growatt_{DEVICE_INSTANCE}/Position',
                    POSITION,
                    0,
                    0,
                ],
            },
            eventCallback=self.handle_setting_changed,
        )

        for reg in REG:
            value = reg["default"]

            if reg["path"] == "/CustomName":
                value = self.settings["customname"]

            elif reg["path"] == "/Position":
                value = int(self.settings["position"])

            self.service.add_path(
                reg["path"],
                value,
                writeable=reg.get("writeable", False),
                onchangecallback=self.handle_dbus_write,
            )

        self.service.register()

    def handle_setting_changed(self, setting, oldvalue, newvalue):
        logging.info(
            "Setting changed %s: %s -> %s",
            setting,
            oldvalue,
            newvalue,
        )

        if setting == "customname":
            self.service["/CustomName"] = str(newvalue)

        elif setting == "position":
            self.service["/Position"] = int(newvalue)

    def handle_dbus_write(self, path, value):
        try:
            if path == "/CustomName":
                self.settings["customname"] = str(value)

            elif path == "/Position":
                self.settings["position"] = int(value)

            return True

        except Exception as e:
            logging.exception("Unable to write setting: %s", e)
            return False


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )

    GrowattDbus()

    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
