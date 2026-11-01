#!/usr/bin/env python3
"""Install all three standalone drivers and their Venus OS startup services."""

import argparse
import importlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

DRIVERS = ("growatt", "ecoforest", "peblar")
TARGET = Path("/data/dbus-modbus-drivers")
SERVICE_ROOT = Path("/service")
RC = Path("/data/rc.local")
FILES = ("base_modbus_dbus.py", "modbus_codec.py", "modbus_types.py", "install_drivers.py") + tuple(
    name + suffix for name in DRIVERS
    for suffix in ("_dbus.py", "_dbus_config.py", "_dbus_registers.py")
)
BEGIN = "# BEGIN victron-modbus-drivers"
END = "# END victron-modbus-drivers"


def startup_content(original):
    """Insert our hook before a final exit, keeping other startup commands."""
    if original.count(BEGIN) != original.count(END) or original.count(BEGIN) > 1:
        raise RuntimeError("Invalid installer markers in /data/rc.local")
    if BEGIN in original:
        pattern = re.escape(BEGIN) + r"\n.*?" + re.escape(END) + r"\n?"
        original = re.sub(pattern, "", original, flags=re.DOTALL)
    block = (BEGIN + "\n"
             '/bin/sh /data/dbus-modbus-drivers/start-services.sh || '
             'echo "Could not start Modbus drivers" >&2\n' + END + "\n")
    match = re.search(r"^exit(?:[ \t]+[^\n]*)?$", original, re.MULTILINE)
    if match:
        return original[:match.start()] + block + original[match.start():]
    return original.rstrip() + "\n\n" + block


def write_executable(path, content):
    temporary = path.with_name(path.name + ".new")
    # open() supports newline on the older Python versions shipped by Venus.
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    temporary.chmod(0o755)
    temporary.replace(path)


def check_service_links(target, service_root):
    for name in DRIVERS:
        link = service_root / ("dbus-" + name)
        expected = target / "services" / link.name
        if os.path.lexists(link) and (
            not link.is_symlink() or os.readlink(link) != str(expected)
        ):
            raise RuntimeError(
                "{} belongs to another installation. Stop and relocate that "
                "service first; it will not be overwritten.".format(link)
            )


def preflight(source):
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        raise RuntimeError("Run this installer as root on the Cerbo")
    if not Path("/service").is_dir():
        raise RuntimeError("/service is missing; run this on Venus OS")
    for command in ("python3", "svc", "svstat", "multilog", "sh"):
        if not shutil.which(command):
            raise RuntimeError("Required command is missing: " + command)
    for filename in FILES + ("start-services.sh",):
        if not (source / filename).is_file():
            raise RuntimeError("Missing source file: " + filename)
    for filename in FILES:
        compile((source / filename).read_bytes(), filename, "exec")
    sys.path.insert(0, "/opt/victronenergy/dbus-systemcalc-py/ext/velib_python")
    sys.path.insert(0, "/data/velib_python")
    for module in ("dbus.mainloop.glib", "gi.repository.GLib",
                   "pymodbus.client.sync", "settingsdevice", "vedbus"):
        try:
            importlib.import_module(module)
        except ImportError as error:
            raise RuntimeError(
                "Missing/incompatible Python dependency: {} ({}). "
                "The drivers require pymodbus 2.x (client.sync).".format(module, error)
            ) from error
    for name in DRIVERS:
        config = TARGET / (name + "_dbus_config.py")
        if not config.exists():
            config = source / config.name
        values = {}
        exec(compile(config.read_bytes(), str(config), "exec"), values)
        for key in ("HOST", "PORT", "UNIT_ID", "DEVICE_INSTANCE", "POLL_INTERVAL_MS"):
            if key not in values:
                raise RuntimeError("{} is missing {}".format(config, key))
        print("{}: host={} port={} unit={} instance={}".format(
            name, values["HOST"], values["PORT"], values["UNIT_ID"], values["DEVICE_INSTANCE"]
        ))
    check_service_links(TARGET, SERVICE_ROOT)
    if Path("/data/rc.local.disabled").exists():
        raise RuntimeError("/data/rc.local.disabled exists; the startup hook is disabled")
    rc = RC
    content = rc.read_text() if rc.exists() else "#!/bin/sh\n"
    if not content.startswith(("#!/bin/sh", "#!/bin/bash")):
        raise RuntimeError("/data/rc.local must be a sh or bash script")
    updated = startup_content(content)
    subprocess.run(["sh", "-n"], input=updated, universal_newlines=True, check=True)
    subprocess.run(["sh", "-n", str(source / "start-services.sh")], check=True)
    return updated


def install(source, rc_content):
    TARGET.mkdir(parents=True, exist_ok=True)
    for name in DRIVERS:
        link = SERVICE_ROOT / ("dbus-" + name)
        if link.is_symlink() and (link / "supervise/ok").exists():
            subprocess.run(["svc", "-d", str(link)], check=True)
            for attempt in range(50):
                status = subprocess.check_output(["svstat", str(link)], universal_newlines=True)
                if ": down " in status:
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("Service did not stop: " + str(link))
    for filename in FILES:
        destination = TARGET / filename
        if filename.endswith("_config.py") and destination.exists():
            print("Keeping configuration: " + str(destination))
            continue
        if (source / filename).resolve() != destination.resolve():
            shutil.copy2(source / filename, destination)
    write_executable(TARGET / "start-services.sh", (source / "start-services.sh").read_text())
    for name in DRIVERS:
        service = TARGET / "services" / ("dbus-" + name)
        (service / "log").mkdir(parents=True, exist_ok=True)
        (service / "down").touch()
        write_executable(service / "run", (
            "#!/bin/sh\nexec 2>&1\n"
            "cd /data/dbus-modbus-drivers || exit 1\n"
            "exec python3 -u {}_dbus.py\n".format(name)
        ))
        write_executable(service / "log/run", (
            "#!/bin/sh\nmkdir -p /var/log/dbus-{0} || exit 1\n"
            "exec multilog t s262144 n3 /var/log/dbus-{0}\n".format(name)
        ))
    rc = RC
    if rc.exists():
        backup = rc.with_name("rc.local.before-modbus-drivers")
        if not backup.exists():
            shutil.copy2(rc, backup)
    write_executable(rc, rc_content)
    subprocess.run(["sh", str(TARGET / "start-services.sh")], check=True)
    print("Installed. All three services are enabled for boot.")
    print("Check: svstat /service/dbus-growatt /service/dbus-ecoforest /service/dbus-peblar")
    print("Inspect /var/log/dbus-NAME/current to confirm device communication.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check prerequisites without installing")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    try:
        rc_content = preflight(source)
        if args.check:
            print("Preflight checks passed; nothing changed.")
        else:
            install(source, rc_content)
    except (OSError, RuntimeError, subprocess.CalledProcessError, SyntaxError) as error:
        print("Installation failed: {}".format(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
