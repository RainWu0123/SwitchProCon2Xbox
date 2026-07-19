"""
Input Mapper
Maps Switch Pro Controller inputs to Xbox 360 controller inputs.
Supports Nintendo layout (position-based) and Xbox layout (label-based).

Hot path is allocation-free: translate_into() writes into a reusable MappedState.
"""

import math
import vgamepad as vg
from controller_reader import ControllerState


class MappedState:
    """Reusable output of InputMapper.translate_into (no per-frame alloc)."""
    __slots__ = (
        "buttons",  # XUSB button bitmask (int)
        "lx", "ly", "rx", "ry",
        "lt", "rt",
    )

    def __init__(self):
        self.buttons = 0
        self.lx = self.ly = self.rx = self.ry = 0
        self.lt = self.rt = 0


class InputMapper:
    """Maps Switch Pro Controller state to Xbox 360 controller state."""

    _FACE = {
        "nintendo": (
            ("a", vg.XUSB_BUTTON.XUSB_GAMEPAD_B),
            ("b", vg.XUSB_BUTTON.XUSB_GAMEPAD_A),
            ("x", vg.XUSB_BUTTON.XUSB_GAMEPAD_Y),
            ("y", vg.XUSB_BUTTON.XUSB_GAMEPAD_X),
        ),
        "xbox": (
            ("a", vg.XUSB_BUTTON.XUSB_GAMEPAD_A),
            ("b", vg.XUSB_BUTTON.XUSB_GAMEPAD_B),
            ("x", vg.XUSB_BUTTON.XUSB_GAMEPAD_X),
            ("y", vg.XUSB_BUTTON.XUSB_GAMEPAD_Y),
        ),
    }

    _COMMON = (
        ("l", vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER),
        ("r", vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER),
        ("plus", vg.XUSB_BUTTON.XUSB_GAMEPAD_START),
        ("minus", vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK),
        ("home", vg.XUSB_BUTTON.XUSB_GAMEPAD_GUIDE),
        ("l_stick_click", vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB),
        ("r_stick_click", vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB),
        ("dpad_up", vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP),
        ("dpad_down", vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN),
        ("dpad_left", vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT),
        ("dpad_right", vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT),
    )

    def __init__(
        self,
        layout: str = "xbox",
        deadzone: float = 0.05,
        invert_y: bool = True,
    ):
        if layout not in self._FACE:
            raise ValueError(f"Unknown layout: {layout!r}")
        self.layout = layout
        self.deadzone = max(0.0, min(0.99, float(deadzone)))
        self.invert_y = invert_y
        self._inv_center = 1.0 / 2048.0
        self._dz = self.deadzone
        self._dz_scale_den = 1.0 - self.deadzone  # always >= 0.01
        # Pre-bind getattr targets once: (attr_name, flag_int)
        self._button_map = tuple(
            (attr, int(flag))
            for attr, flag in (self._FACE[layout] + self._COMMON)
        )

    def map_buttons(self, state: ControllerState) -> list:
        """Return list of pressed XUSB button flags (compat / tests)."""
        return [
            flag for attr, flag in self._button_map
            if getattr(state, attr, False)
        ]

    def map_buttons_mask(self, state: ControllerState) -> int:
        """Return combined XUSB wButtons bitmask."""
        mask = 0
        for attr, flag in self._button_map:
            if getattr(state, attr, False):
                mask |= flag
        return mask

    def map_triggers(self, state: ControllerState) -> tuple:
        return (255 if state.zl else 0, 255 if state.zr else 0)

    def map_stick(self, raw_x: int, raw_y: int) -> tuple:
        """Convert 12-bit stick values to Xbox 16-bit signed range."""
        inv = self._inv_center
        nx = (raw_x - 2048) * inv
        ny = (raw_y - 2048) * inv
        if self.invert_y:
            ny = -ny

        if nx > 1.0:
            nx = 1.0
        elif nx < -1.0:
            nx = -1.0
        if ny > 1.0:
            ny = 1.0
        elif ny < -1.0:
            ny = -1.0

        mag_sq = nx * nx + ny * ny
        dz = self._dz
        if mag_sq <= dz * dz:
            return (0, 0)

        magnitude = math.sqrt(mag_sq)
        scale = (magnitude - dz) / self._dz_scale_den
        if scale > 1.0:
            scale = 1.0
        scale /= magnitude
        nx *= scale
        ny *= scale

        xbox_x = int(nx * 32767)
        xbox_y = int(ny * 32767)
        if xbox_x > 32767:
            xbox_x = 32767
        elif xbox_x < -32768:
            xbox_x = -32768
        if xbox_y > 32767:
            xbox_y = 32767
        elif xbox_y < -32768:
            xbox_y = -32768
        return (xbox_x, xbox_y)

    def translate_into(self, state: ControllerState, out: MappedState) -> MappedState:
        """Hot path: fill `out` in place (no dict/list allocations)."""
        out.buttons = self.map_buttons_mask(state)
        out.lx, out.ly = self.map_stick(state.left_stick_x, state.left_stick_y)
        out.rx, out.ry = self.map_stick(state.right_stick_x, state.right_stick_y)
        out.lt = 255 if state.zl else 0
        out.rt = 255 if state.zr else 0
        return out

    def translate(self, state: ControllerState) -> dict:
        """Dict API for tests / external callers."""
        m = MappedState()
        self.translate_into(state, m)
        return {
            "buttons": m.buttons,
            "left_stick": (m.lx, m.ly),
            "right_stick": (m.rx, m.ry),
            "left_trigger": m.lt,
            "right_trigger": m.rt,
        }
