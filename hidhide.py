"""
Device Hiding Module
Hides the physical Switch controller from Windows/games using HidHide.
Requires Administrator privileges and HidHide driver to be installed.
"""

import subprocess
import sys
import os
import ctypes
import json
from typing import List, Optional


def is_admin() -> bool:
    """Check if the current process has administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def find_hidhide_cli() -> Optional[str]:
    """Locate HidHideCLI.exe via env var, common install paths, or PATH."""
    env_path = os.environ.get("HIDHIDE_CLI")
    if env_path and os.path.isfile(env_path):
        return env_path

    candidates = [
        r"C:\Program Files\Nefarius Software Solutions\HidHide\x64\HidHideCLI.exe",
        r"C:\Program Files\Nefarius Software Solutions\HidHide\x86\HidHideCLI.exe",
        r"C:\Program Files (x86)\Nefarius Software Solutions\HidHide\x64\HidHideCLI.exe",
        r"C:\Program Files (x86)\Nefarius Software Solutions\HidHide\x86\HidHideCLI.exe",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path

    # Fallback: look on PATH
    for name in ("HidHideCLI.exe", "HidHideCLI"):
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            candidate = os.path.join(directory.strip('"'), name)
            if os.path.isfile(candidate):
                return candidate
    return None


class DeviceHider:
    """
    Hides the physical Switch controller from games using HidHide.
    """

    def __init__(self, cli_path: Optional[str] = None):
        self.cli_path = cli_path or find_hidhide_cli()
        self.disabled_devices: List[str] = []  # Kept for main.py compatibility
        self.available = bool(is_admin() and self.cli_path)
        if self.available:
            # Temporarily disable cloaking so we can find/connect the controller
            # (no taskkill on every start — only force_reset kills hung CLIs)
            self._run_cli(["--cloak-off"])

    def _run_cli(self, args: List[str]) -> bool:
        if not self.available or not self.cli_path:
            return False
        try:
            res = subprocess.run(
                [self.cli_path] + args,
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return res.returncode == 0
        except Exception:
            return False

    def find_switch_devices(self) -> List[str]:
        if not self.available:
            return []
        try:
            res = subprocess.run(
                [self.cli_path, "--dev-gaming"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if res.returncode == 0:
                data = json.loads(res.stdout)
                paths = []
                for entry in data:
                    for dev in entry.get("devices", []):
                        inst_path = dev.get("deviceInstancePath")
                        if inst_path and "057E" in inst_path.upper():
                            paths.append(inst_path)
                return paths
        except Exception:
            pass
        return []

    def setup(self) -> bool:
        """
        Register our app, cloak on, and hide the Switch controller(s).
        """
        if not self.available:
            return False

        switch_devices = self.find_switch_devices()
        if not switch_devices:
            return False

        # Register current Python interpreter so it can still read hidden devices
        py_exe = os.path.abspath(sys.executable)
        self._run_cli(["--app-reg", py_exe])

        hidden_any = False
        for dev_path in switch_devices:
            if self._run_cli(["--dev-hide", dev_path]):
                if dev_path not in self.disabled_devices:
                    self.disabled_devices.append(dev_path)
                hidden_any = True

        if hidden_any:
            self._run_cli(["--cloak-on"])
            return True

        return False

    def cleanup(self):
        """
        Unhide devices we hid and unregister our app on exit.
        """
        if not self.available:
            return

        for dev_path in self.disabled_devices:
            self._run_cli(["--dev-unhide", dev_path])

        # Only turn cloaking off if we were the ones who hid devices this session
        if self.disabled_devices:
            self._run_cli(["--cloak-off"])

        py_exe = os.path.abspath(sys.executable)
        self._run_cli(["--app-unreg", py_exe])

        self.disabled_devices.clear()

    def force_reset(self) -> bool:
        """
        Force-reset ALL HidHide state for Nintendo devices.
        Use this to recover from a crash or when switching to Steam Input.
        """
        if not is_admin():
            return False

        cli = self.cli_path or find_hidhide_cli()
        if not cli:
            return False

        self.cli_path = cli
        old_available = self.available
        self.available = True

        try:
            subprocess.run(
                ["taskkill", "/f", "/im", "HidHideCLI.exe"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            pass

        switch_devices = self.find_switch_devices()
        for dev_path in switch_devices:
            self._run_cli(["--dev-unhide", dev_path])

        self._run_cli(["--cloak-off"])

        py_exe = os.path.abspath(sys.executable)
        self._run_cli(["--app-unreg", py_exe])

        self.disabled_devices.clear()
        self.available = old_available
        return True
