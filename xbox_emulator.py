"""
Xbox 360 Virtual Controller Emulator
Uses vgamepad (ViGEmBus). Hot path writes report fields directly and
skips the kernel update when the state is unchanged.
"""

import time
import vgamepad as vg


class XboxEmulator:
    """Creates and controls a virtual Xbox 360 controller."""

    def __init__(self, retries: int = 3, retry_delay: float = 1.0):
        last_error = None
        self.gamepad = None
        for _ in range(retries):
            try:
                self.gamepad = vg.VX360Gamepad()
                break
            except Exception as e:
                last_error = e
                time.sleep(retry_delay)
        if self.gamepad is None:
            raise RuntimeError(
                f"Failed to create virtual Xbox 360 controller: {last_error}"
            )
        self._active = True
        # Last submitted report snapshot for change detection
        self._last = (0, 0, 0, 0, 0, 0, 0)  # buttons, lx, ly, rx, ry, lt, rt

    @property
    def active(self) -> bool:
        return self._active

    def update(self, buttons, left_stick, right_stick,
               left_trigger: int, right_trigger: int):
        """
        Update virtual pad. `buttons` may be a bitmask (int) or a list of flags.
        Skips ViGEm submit when nothing changed (saves CPU, lower bus chatter).
        """
        if not self._active or self.gamepad is None:
            return

        if isinstance(buttons, int):
            mask = buttons
        else:
            mask = 0
            for btn in buttons:
                mask |= int(btn)

        lx, ly = left_stick
        rx, ry = right_stick
        snap = (mask, lx, ly, rx, ry, left_trigger, right_trigger)
        if snap == self._last:
            return

        try:
            r = self.gamepad.report
            r.wButtons = mask
            r.bLeftTrigger = left_trigger
            r.bRightTrigger = right_trigger
            r.sThumbLX = lx
            r.sThumbLY = ly
            r.sThumbRX = rx
            r.sThumbRY = ry
            self.gamepad.update()
            self._last = snap
        except Exception:
            self._active = False

    def update_mapped(self, m) -> None:
        """Faster entry from MappedState (no tuple packing)."""
        if not self._active or self.gamepad is None:
            return
        snap = (m.buttons, m.lx, m.ly, m.rx, m.ry, m.lt, m.rt)
        if snap == self._last:
            return
        try:
            r = self.gamepad.report
            r.wButtons = m.buttons
            r.bLeftTrigger = m.lt
            r.bRightTrigger = m.rt
            r.sThumbLX = m.lx
            r.sThumbLY = m.ly
            r.sThumbRX = m.rx
            r.sThumbRY = m.ry
            self.gamepad.update()
            self._last = snap
        except Exception:
            self._active = False

    def register_rumble_callback(self, callback):
        if not self.gamepad:
            return
        try:
            self.gamepad.register_notification(callback_function=callback)
        except Exception:
            pass

    def cleanup(self):
        if self.gamepad is not None:
            try:
                self.gamepad.reset()
                self.gamepad.update()
            except Exception:
                pass
            try:
                del self.gamepad
            except Exception:
                pass
            self.gamepad = None
        self._active = False
        self._last = (0, 0, 0, 0, 0, 0, 0)
