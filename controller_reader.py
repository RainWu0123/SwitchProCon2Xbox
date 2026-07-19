"""
Switch Pro Controller HID Reader
Handles USB connection, handshake, and input report parsing for
both the original Switch Pro Controller and Switch 2 Pro Controller.
"""

import hid
import time
from dataclasses import dataclass, field
from typing import Optional

VENDOR_ID = 0x057E
PRODUCT_IDS = {
    0x2009: "Switch Pro Controller",
    0x2069: "Switch 2 Pro Controller",
}


@dataclass
class ControllerState:
    """Represents the current state of the Switch Pro Controller."""
    # Face buttons
    a: bool = False
    b: bool = False
    x: bool = False
    y: bool = False
    # Shoulder buttons
    l: bool = False
    r: bool = False
    zl: bool = False
    zr: bool = False
    # System buttons
    plus: bool = False
    minus: bool = False
    home: bool = False
    capture: bool = False
    # Stick clicks
    l_stick_click: bool = False
    r_stick_click: bool = False
    # Back grip buttons (Switch 2 only)
    gl: bool = False
    gz: bool = False
    # D-pad
    dpad_up: bool = False
    dpad_down: bool = False
    dpad_left: bool = False
    dpad_right: bool = False
    # Analog sticks (12-bit: 0-4095, center ~2048)
    left_stick_x: int = 2048
    left_stick_y: int = 2048
    right_stick_x: int = 2048
    right_stick_y: int = 2048
    # Battery
    battery_level: int = 0
    # Raw Diagnostic bytes
    raw_b3: int = 0
    raw_b4: int = 0
    raw_b5: int = 0


class SwitchProController:
    """Manages communication with a Switch Pro Controller over USB HID."""

    # Report IDs that carry full/standard button+stick data
    _STANDARD_REPORTS = frozenset((0x30, 0x31, 0x32, 0x33, 0x21, 0x09))

    def __init__(self):
        self.device: Optional[hid.device] = None
        self.state = ControllerState()
        self._packet_number = 0
        self.controller_name = ""
        self.product_id = 0
        self._connected = False
        self._blocking = False  # track current HID blocking mode
        # Reusable 64-byte output buffer for writes (avoids per-call list alloc)
        self._out_buf = [0] * 64

    @property
    def connected(self) -> bool:
        return self._connected

    def find_and_connect(self, retries: int = 3) -> bool:
        """Scan for and open a supported Switch Pro Controller with retry."""
        for attempt in range(retries):
            for pid, name in PRODUCT_IDS.items():
                try:
                    dev = hid.device()
                    dev.open(VENDOR_ID, pid)
                    dev.set_nonblocking(True)
                    self.device = dev
                    self.controller_name = name
                    self.product_id = pid
                    self._connected = True
                    return True
                except Exception:
                    continue
            if attempt < retries - 1:
                time.sleep(0.5)
        return False

    def _set_blocking(self, blocking: bool) -> None:
        """Set HID blocking mode only when it actually changes."""
        if not self.device or self._blocking == blocking:
            return
        self.device.set_nonblocking(not blocking)
        self._blocking = blocking

    def _write(self, data: list):
        """Send a padded 64-byte report to the controller."""
        if not self.device:
            raise RuntimeError("Controller device is not connected")
        buf = self._out_buf
        n = len(data)
        if n > 64:
            n = 64
        for i in range(n):
            buf[i] = data[i]
        for i in range(n, 64):
            buf[i] = 0
        self.device.write(buf)

    def _read(self, timeout_ms: int = 500) -> Optional[list]:
        """Read a report from the controller with timeout."""
        if not self.device:
            return None
        self._set_blocking(True)
        data = self.device.read(64, timeout_ms)
        return data if data else None

    def _send_subcmd(self, subcmd_id: int, subcmd_data: list = None):
        """Send an 0x01 output report with a subcommand."""
        if subcmd_data is None:
            subcmd_data = []
        buf = [0x01, self._packet_number & 0x0F]
        # Neutral rumble data
        buf += [0x00, 0x01, 0x40, 0x40, 0x00, 0x01, 0x40, 0x40]
        buf.append(subcmd_id)
        buf += subcmd_data
        self._write(buf)
        self._packet_number = (self._packet_number + 1) & 0x0F
        time.sleep(0.02)
        return self._read(timeout_ms=500)

    def initialize(self) -> bool:
        """
        Perform the USB handshake sequence to enable standard input reports.
        Sequence: 80 01 → 80 02 → 80 03 → 80 02 → 80 04 → set mode 0x30
        """
        try:
            # Step 1: Get device info
            self._write([0x80, 0x01])
            resp = self._read(1000)
            if not resp:
                return False

            # Step 2: First handshake
            self._write([0x80, 0x02])
            self._read(1000)

            # Step 3: Switch to 3Mbit baudrate
            self._write([0x80, 0x03])
            self._read(1000)

            # Step 4: Second handshake (required after baud switch)
            self._write([0x80, 0x02])
            self._read(1000)

            # Step 5: Force USB mode (prevent Bluetooth timeout)
            self._write([0x80, 0x04])
            time.sleep(0.5)

            # Flush any pending data
            self._blocking = False
            self.device.set_nonblocking(True)
            for _ in range(20):
                self.device.read(64)
                time.sleep(0.01)
            # Main loop prefers blocking reads with timeout
            self._set_blocking(True)

            # Step 6: Set input report mode to 0x30 (standard full, 120Hz)
            self._send_subcmd(0x03, [0x30])
            time.sleep(0.1)

            # Step 7: Enable vibration (CRITICAL for rumble to work)
            # Subcommand 0x48 with arg 0x01 = enable
            self._send_subcmd(0x48, [0x01])
            time.sleep(0.1)

            # Step 8: Set player LED (Player 1 = first LED on)
            self._send_subcmd(0x30, [0x01])
            time.sleep(0.1)

            return True

        except Exception as e:
            print(f"  Initialization error: {e}")
            return False

    def send_keepalive(self):
        """Send a periodic neutral rumble packet as a keepalive to prevent auto-sleep timeout."""
        if not self.device or not self._connected:
            return
        try:
            if self.product_id == 0x2069:
                # Switch 2 uses 0x02 report format
                buf = [0] * 64
                buf[0] = 0x02
                buf[1] = buf[17] = 0x50 | (self._packet_number & 0x0F)
                self.device.write(buf)
            else:
                # Switch 1 uses 0x10 format
                buf = [0x10, self._packet_number & 0x0F]
                buf += [0x00, 0x01, 0x40, 0x40, 0x00, 0x01, 0x40, 0x40]
                self._write(buf)
                
            self._packet_number = (self._packet_number + 1) & 0x0F
        except Exception:
            self._connected = False

    def send_rumble(self, large_motor: int, small_motor: int):
        """
        Send rumble/vibration to the physical Switch controller.
        Automatically uses the correct protocol for Gen 1 (0x10) or Gen 2 (0x02).
        """
        if not self.device or not self._connected:
            return
        try:
            if self.product_id == 0x2069:
                # Switch 2 Pro Controller uses procon2tool 0x02 haptic format
                intensity = max(large_motor, small_motor)
                haptic_data = self._encode_switch2_haptic(intensity)

                buf = [0] * 64
                buf[0] = 0x02
                buf[1] = buf[17] = 0x50 | (self._packet_number & 0x0F)
                for i in range(5):
                    buf[2 + i] = haptic_data[i]
                    buf[18 + i] = haptic_data[i]
                self.device.write(buf)
            else:
                # Switch 1 format
                left_rumble = self._encode_rumble(large_motor, small_motor)
                right_rumble = self._encode_rumble(large_motor, small_motor)
                buf = [0x10, self._packet_number & 0x0F]
                buf += left_rumble + right_rumble
                self._write(buf)

            self._packet_number = (self._packet_number + 1) & 0x0F
        except Exception:
            # Rumble is best-effort; never tear down the session for it.
            return

    def test_rumble(self):
        """Send a short test buzz to confirm rumble is working."""
        if not self.device or not self._connected:
            return
        self.send_rumble(200, 100)
        time.sleep(0.15)
        self.send_rumble(0, 0)

    @staticmethod
    def _encode_switch2_haptic(intensity: int) -> list:
        """Get 5-byte haptic pattern for Switch 2 Pro Controller based on intensity."""
        if intensity == 0:
            return [0x00, 0x00, 0x00, 0x00, 0x00]
        elif intensity < 64:
            return [0x3f, 0x19, 0xf0, 0x99, 0x00]  # Weak
        elif intensity < 128:
            return [0x4b, 0x7d, 0x80, 0x5a, 0x02]  # Med-Weak
        elif intensity < 192:
            return [0x75, 0x15, 0x73, 0x1e, 0x11]  # Medium
        else:
            return [0x93, 0x35, 0x36, 0x1c, 0x0d]  # Strong

    @staticmethod
    def _encode_rumble(large_motor: int, small_motor: int) -> list:
        """
        Encode Xbox motor values into 4-byte Switch LRA rumble data (Switch 1 only).
        Returns [byte0, byte1, byte2, byte3].
        """
        if large_motor == 0 and small_motor == 0:
            return [0x00, 0x01, 0x40, 0x40]

        # --- High Band (small_motor = high-frequency buzz) ---
        if small_motor > 0:
            hf_freq = 0x74
            hf_amp_raw = int((small_motor / 255.0) * 0x64)
            byte0 = hf_freq
            byte1 = ((hf_amp_raw & 0x7F) << 1) | 0x01
        else:
            byte0 = 0x00
            byte1 = 0x01

        # --- Low Band (large_motor = low-frequency rumble) ---
        if large_motor > 0:
            lf_freq = 0x40      # ~160Hz low band fixed frequency
            # Amplitude: scale 0-255 → 0x40-0x72 (safe range, 0x40=silent, 0x72=max safe)
            lf_amp = 0x40 + int((large_motor / 255.0) * (0x72 - 0x40))
            lf_amp = max(0x40, min(0x72, lf_amp))
            byte2 = lf_freq
            byte3 = lf_amp
        else:
            byte2 = 0x40
            byte3 = 0x40

        return [byte0, byte1, byte2, byte3]

    def _handle_report(self, data) -> Optional[ControllerState]:
        """Parse a raw HID report into ControllerState, or return None."""
        if not data or len(data) < 12:
            return None

        report_id = data[0]

        if report_id in self._STANDARD_REPORTS:
            self._parse_standard(data)
            return self.state
        if report_id == 0x3F:
            self._parse_simple(data)
            return self.state

        return None

    def read_input(self) -> Optional[ControllerState]:
        """Read and parse one input report (non-blocking). Returns state or None."""
        if not self.device:
            return None
        try:
            self._set_blocking(False)
            data = self.device.read(64)
        except Exception:
            self._connected = False
            return None
        return self._handle_report(data)

    def read_input_blocking(self, timeout_ms: int = 8) -> Optional[ControllerState]:
        """
        Read and parse one input report using blocking I/O with timeout.
        Keeps the device in blocking mode (no per-call mode flip).

        Args:
            timeout_ms: Max time to wait for data (default 8ms = ~125Hz)
        """
        if not self.device:
            return None
        try:
            self._set_blocking(True)
            data = self.device.read(64, timeout_ms)
        except Exception:
            self._connected = False
            return None
        return self._handle_report(data)

    def read_latest(self, timeout_ms: int = 8) -> Optional[ControllerState]:
        """
        Wait for one report, then drain the HID queue and keep only the newest.
        Cuts input latency when the consumer briefly lags behind 120Hz.
        """
        state = self.read_input_blocking(timeout_ms)
        if state is None:
            return None
        # Drain without waiting — always apply the freshest packet
        while True:
            more = self.read_input()
            if more is None:
                break
            state = more
        # Restore blocking mode for next wait
        self._set_blocking(True)
        return state

    def _parse_standard(self, data: list):
        """Parse a standard full input report (0x30 / 0x21 / 0x09)."""
        if len(data) < 12:
            return

        report_id = data[0]

        # Battery (high nibble of byte 2)
        self.state.battery_level = (data[2] >> 4) & 0x0F

        b3 = data[3]
        b4 = data[4]
        b5 = data[5]

        self.state.raw_b3 = b3
        self.state.raw_b4 = b4
        self.state.raw_b5 = b5

        if report_id == 0x09:
            # === Switch 2 Pro Controller wired USB mapping ===
            # Byte 3: Right half of controller (Face buttons, R/ZR, Plus)
            self.state.b = bool(b3 & 0x01)
            self.state.a = bool(b3 & 0x02)
            self.state.y = bool(b3 & 0x04)
            self.state.x = bool(b3 & 0x08)
            self.state.r = bool(b3 & 0x10)
            self.state.zr = bool(b3 & 0x20)
            self.state.plus = bool(b3 & 0x40)

            # Byte 4: Left half of controller (D-pad, L/ZL, Minus)
            self.state.dpad_down = bool(b4 & 0x01)
            self.state.dpad_right = bool(b4 & 0x02)
            self.state.dpad_left = bool(b4 & 0x04)
            self.state.dpad_up = bool(b4 & 0x08)
            self.state.l = bool(b4 & 0x10)
            self.state.zl = bool(b4 & 0x20)
            self.state.minus = bool(b4 & 0x40)

            # Byte 5: Center & back of controller (Home, Capture, Back buttons, C clicks)
            self.state.home = bool(b5 & 0x01)
            self.state.capture = bool(b5 & 0x02)
            self.state.gz = bool(b5 & 0x04)  # GZ back grip button
            self.state.gl = bool(b5 & 0x08)  # GL back grip button
            self.state.l_stick_click = bool(b5 & 0x10)  # C key acts as L3
            self.state.r_stick_click = bool(b5 & 0x20)  # R3 click

        else:
            # === Switch 1 Pro Controller standard mapping ===
            # Byte 3: Right-side buttons
            self.state.y = bool(b3 & 0x01)
            self.state.x = bool(b3 & 0x02)
            self.state.b = bool(b3 & 0x04)
            self.state.a = bool(b3 & 0x08)
            self.state.r = bool(b3 & 0x40)
            self.state.zr = bool(b3 & 0x80)

            # Byte 4: Shared buttons
            self.state.minus = bool(b4 & 0x01)
            self.state.plus = bool(b4 & 0x02)
            self.state.r_stick_click = bool(b4 & 0x04)
            self.state.l_stick_click = bool(b4 & 0x08)
            self.state.home = bool(b4 & 0x10)
            self.state.capture = bool(b4 & 0x20)

            # Byte 5: Left-side buttons
            self.state.dpad_down = bool(b5 & 0x01)
            self.state.dpad_up = bool(b5 & 0x02)
            self.state.dpad_right = bool(b5 & 0x04)
            self.state.dpad_left = bool(b5 & 0x08)
            self.state.l = bool(b5 & 0x40)
            self.state.zl = bool(b5 & 0x80)

        # --- Analog sticks (same for both Switch 1 & 2) ---
        # Left stick: bytes 6-8
        self.state.left_stick_x = data[6] | ((data[7] & 0x0F) << 8)
        self.state.left_stick_y = (data[7] >> 4) | (data[8] << 4)
        # Right stick: bytes 9-11
        self.state.right_stick_x = data[9] | ((data[10] & 0x0F) << 8)
        self.state.right_stick_y = (data[10] >> 4) | (data[11] << 4)

    def _parse_simple(self, data: list):
        """Parse a simple HID input report (0x3F) - fallback mode."""
        if len(data) < 4:
            return

        # Byte 2: shared / system buttons
        b2 = data[2]
        self.state.minus = bool(b2 & 0x01)
        self.state.plus = bool(b2 & 0x02)
        self.state.l_stick_click = bool(b2 & 0x04)
        self.state.r_stick_click = bool(b2 & 0x08)
        self.state.home = bool(b2 & 0x10)
        self.state.capture = bool(b2 & 0x20)

        # Byte 3: hat switch is the authoritative d-pad in simple mode
        hat = data[3]
        hat_map = {
            0: (True, False, False, False),   # Up
            1: (True, True, False, False),    # Up-Right
            2: (False, True, False, False),   # Right
            3: (False, True, True, False),    # Down-Right
            4: (False, False, True, False),   # Down
            5: (False, False, True, True),    # Down-Left
            6: (False, False, False, True),   # Left
            7: (True, False, False, True),    # Up-Left
            8: (False, False, False, False),  # Neutral
        }
        if hat in hat_map:
            u, r, d, l = hat_map[hat]
            self.state.dpad_up = u
            self.state.dpad_right = r
            self.state.dpad_down = d
            self.state.dpad_left = l
        else:
            # Fallback to bit flags in byte 1 when hat is unknown
            b1 = data[1]
            self.state.dpad_down = bool(b1 & 0x01)
            self.state.dpad_right = bool(b1 & 0x02)
            self.state.dpad_left = bool(b1 & 0x04)
            self.state.dpad_up = bool(b1 & 0x08)

        # Pro Controller stick data: bytes 4-11 (16-bit per axis)
        if len(data) >= 12:
            lx = data[4] | (data[5] << 8)
            ly = data[6] | (data[7] << 8)
            rx = data[8] | (data[9] << 8)
            ry = data[10] | (data[11] << 8)
            # Convert 16-bit (0-65535) to 12-bit (0-4095)
            self.state.left_stick_x = lx >> 4
            self.state.left_stick_y = ly >> 4
            self.state.right_stick_x = rx >> 4
            self.state.right_stick_y = ry >> 4

    def disconnect(self):
        """Gracefully disconnect the controller."""
        if self.device:
            try:
                self._write([0x80, 0x05])
            except Exception:
                pass
            try:
                self.device.close()
            except Exception:
                pass
            self.device = None
            self._connected = False
            self._blocking = False
