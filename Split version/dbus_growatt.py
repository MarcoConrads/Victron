#!/usr/bin/env python3
# /data/dbus-growatt/dbus_growatt.py

import logging
import sys

from gi.repository import GLib
import dbus.mainloop.glib

sys.path.insert(0, "/opt/victronenergy/dbus-systemcalc-py/ext/velib_python")
sys.path.insert(0, "/data/velib_python")

from config import POLL_INTERVAL_MS
from growatt_dbus import GrowattDbus


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )
    inverter = GrowattDbus()
    GLib.timeout_add(POLL_INTERVAL_MS, inverter.poll)
    inverter.poll()
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
