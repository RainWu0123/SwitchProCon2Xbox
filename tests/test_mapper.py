"""Unit tests for InputMapper (no hardware required)."""

import os
import sys
import unittest

# Project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vgamepad as vg
from controller_reader import ControllerState
from mapper import InputMapper


class TestDeadzone(unittest.TestCase):
    def test_deadzone_clamped_to_0_99(self):
        m = InputMapper(deadzone=1.5)
        self.assertEqual(m.deadzone, 0.99)
        # Must not raise ZeroDivisionError
        x, y = m.map_stick(4095, 2048)
        self.assertIsInstance(x, int)

    def test_deadzone_negative_clamped(self):
        m = InputMapper(deadzone=-0.5)
        self.assertEqual(m.deadzone, 0.0)

    def test_center_is_zero(self):
        m = InputMapper(deadzone=0.05, invert_y=False)
        self.assertEqual(m.map_stick(2048, 2048), (0, 0))

    def test_inside_deadzone_is_zero(self):
        m = InputMapper(deadzone=0.1, invert_y=False)
        # ~2% deflection
        self.assertEqual(m.map_stick(2048 + 40, 2048), (0, 0))

    def test_full_deflection_x(self):
        m = InputMapper(deadzone=0.0, invert_y=False)
        x, y = m.map_stick(4095, 2048)
        self.assertGreater(x, 32000)
        self.assertEqual(y, 0)


class TestInvertY(unittest.TestCase):
    def test_invert_y_default_makes_high_raw_y_negative(self):
        # Switch often reports higher Y when stick is pushed down
        m = InputMapper(deadzone=0.0, invert_y=True)
        _, y = m.map_stick(2048, 4095)
        self.assertLess(y, 0)

    def test_no_invert_y_high_raw_is_positive(self):
        m = InputMapper(deadzone=0.0, invert_y=False)
        _, y = m.map_stick(2048, 4095)
        self.assertGreater(y, 0)


class TestLayouts(unittest.TestCase):
    def _face_state(self, **kwargs):
        s = ControllerState()
        for k, v in kwargs.items():
            setattr(s, k, v)
        return s

    def test_xbox_layout_a_maps_to_a(self):
        m = InputMapper(layout="xbox")
        buttons = m.map_buttons(self._face_state(a=True))
        self.assertIn(vg.XUSB_BUTTON.XUSB_GAMEPAD_A, buttons)
        self.assertNotIn(vg.XUSB_BUTTON.XUSB_GAMEPAD_B, buttons)

    def test_nintendo_layout_a_maps_to_b(self):
        m = InputMapper(layout="nintendo")
        buttons = m.map_buttons(self._face_state(a=True))
        self.assertIn(vg.XUSB_BUTTON.XUSB_GAMEPAD_B, buttons)

    def test_nintendo_b_maps_to_a(self):
        m = InputMapper(layout="nintendo")
        buttons = m.map_buttons(self._face_state(b=True))
        self.assertIn(vg.XUSB_BUTTON.XUSB_GAMEPAD_A, buttons)

    def test_shoulders_and_dpad(self):
        m = InputMapper(layout="xbox")
        s = self._face_state(l=True, r=True, dpad_up=True, plus=True)
        buttons = m.map_buttons(s)
        self.assertIn(vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER, buttons)
        self.assertIn(vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, buttons)
        self.assertIn(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, buttons)
        self.assertIn(vg.XUSB_BUTTON.XUSB_GAMEPAD_START, buttons)

    def test_invalid_layout_raises(self):
        with self.assertRaises(ValueError):
            InputMapper(layout="playstation")


class TestTriggers(unittest.TestCase):
    def test_zl_zr_digital(self):
        m = InputMapper()
        s = ControllerState(zl=True, zr=False)
        lt, rt = m.map_triggers(s)
        self.assertEqual(lt, 255)
        self.assertEqual(rt, 0)

    def test_translate_uses_map_triggers(self):
        m = InputMapper(layout="xbox", deadzone=0.0, invert_y=False)
        s = ControllerState(zl=True, zr=True, a=True, left_stick_x=2048, left_stick_y=2048)
        out = m.translate(s)
        self.assertEqual(out["left_trigger"], 255)
        self.assertEqual(out["right_trigger"], 255)
        # buttons is now a bitmask for the hot path
        self.assertTrue(out["buttons"] & int(vg.XUSB_BUTTON.XUSB_GAMEPAD_A))
        self.assertEqual(out["left_stick"], (0, 0))

    def test_translate_into_no_alloc_shape(self):
        from mapper import MappedState
        m = InputMapper(layout="xbox", deadzone=0.0, invert_y=False)
        out = MappedState()
        s = ControllerState(b=True, left_stick_x=4095, left_stick_y=2048)
        m.translate_into(s, out)
        self.assertTrue(out.buttons & int(vg.XUSB_BUTTON.XUSB_GAMEPAD_B))
        self.assertGreater(out.lx, 0)
        self.assertEqual(out.ly, 0)


if __name__ == "__main__":
    unittest.main()
