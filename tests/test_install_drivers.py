"""Exercise installer updates without touching actual Cerbo services."""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "Split version"
spec = importlib.util.spec_from_file_location("install_drivers", SOURCE / "install_drivers.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def test_boot_hook_preserves_commands_and_precedes_exit(self):
        original = "#!/bin/sh\necho existing\nexit 0\n"
        updated = installer.startup_content(original)
        self.assertIn("echo existing\n", updated)
        self.assertLess(updated.index(installer.BEGIN), updated.index("exit 0"))
        self.assertEqual(installer.startup_content(updated), updated)

    def test_hook_without_exit_is_idempotent(self):
        updated = installer.startup_content("#!/bin/sh\necho existing\n")
        self.assertEqual(installer.startup_content(updated), updated)
        with self.assertRaises(RuntimeError):
            installer.startup_content("#!/bin/sh\n" + installer.BEGIN)

    def test_refuses_foreign_service(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dbus-growatt").mkdir()
            with self.assertRaisesRegex(RuntimeError, "another installation"):
                installer.check_service_links(root / "drivers", root)

    def test_install_and_update_preserve_config_and_original_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "drivers"
            service_root = root / "service"
            service_root.mkdir()
            rc = root / "rc.local"
            original = "#!/bin/sh\necho keep-me\nexit 0\n"
            rc.write_text(original)
            with patch.object(installer, "TARGET", target), \
                    patch.object(installer, "SERVICE_ROOT", service_root), \
                    patch.object(installer, "RC", rc), \
                    patch.object(installer.subprocess, "run") as run:
                installer.install(SOURCE, installer.startup_content(original))
                run.assert_called_with(["sh", str(target / "start-services.sh")], check=True)
                config = target / "growatt_dbus_config.py"
                config.write_text('HOST = "my-existing-device"\n')
                # Simulate an outdated installed module, then install again.
                (target / "modbus_codec.py").write_text("# outdated\n")
                installer.install(SOURCE, installer.startup_content(rc.read_text()))
                self.assertEqual(config.read_text(), 'HOST = "my-existing-device"\n')
                self.assertEqual((target / "modbus_codec.py").read_bytes(),
                                 (SOURCE / "modbus_codec.py").read_bytes())
                self.assertEqual((root / "rc.local.before-modbus-drivers").read_text(), original)
                self.assertEqual(rc.read_text().count(installer.BEGIN), 1)
                for name in installer.DRIVERS:
                    service = target / "services" / ("dbus-" + name)
                    self.assertIn("exec python3 -u " + name + "_dbus.py", (service / "run").read_text())
                    self.assertIn("multilog t s262144 n3", (service / "log/run").read_text())
                    self.assertNotIn(b"\r", (service / "run").read_bytes())
                # Also check generated shell syntax when Git's shell is available.
                shell = Path("C:/Program Files/Git/bin/bash.exe")
                if shell.exists():
                    scripts = [rc, target / "start-services.sh"]
                    scripts += list((target / "services").glob("*/run"))
                    scripts += list((target / "services").glob("*/log/run"))
                    # subprocess.run was mocked; use Popen for the real syntax check.
                    for script in scripts:
                        process = subprocess.Popen([str(shell), "-n", str(script)],
                                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        _, error = process.communicate()
                        self.assertEqual(process.returncode, 0, error.decode())


if __name__ == "__main__":
    unittest.main()
