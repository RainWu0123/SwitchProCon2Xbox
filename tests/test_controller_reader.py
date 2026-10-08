"""Unit tests for Switch report parsing (no hardware required)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controller_reader import SwitchProController, ControllerState


def _base_report(report_id: int = 0x30) -> list:
    """Minimal 12+ byte report with centered sticks."""
    data = [0] * 64
    data[0] = report_id
    data[2] = 0x80  # battery high nibble = 8
    # Left stick center 2048: low 8 = 0x00, mid nibble 0x0, high of Y etc.
    # left_x = data[6] | ((data[7] & 0x0F) << 8) = 2048 = 0x800
    data[6] = 0x00
    data[7] = 0x08  # low nibble of high byte for X = 8 → 0x800
    # left_y = (data[7] >> 4) | (data[8] << 4) = 2048 = 0x800
    # data[7] high nibble already 0, so data[8] << 4 = 0x800 → data[8] = 0x80
    data[7] = 0x08  # X high nibble 8, Y low nibble 0
    data[8] = 0x80
    # Fix left stick properly:
    # x=2048=0x800 → data[6]=0x00, data[7] low = 0x8
    # y=2048=0x800 → data[7] high = 0x0, data[8] = 0x80
    # right stick bytes 9-11 same pattern
    data[9] = 0x00
    data[10] = 0x08
    data[11] = 0x80
    return data


class TestParseStandardSwitch1(unittest.TestCase):
    def setUp(self):
        self.ctrl = SwitchProController()
        self.ctrl.product_id = 0x2009

    def test_face_buttons_switch1(self):
        data = _base_report(0x30)
        # Switch 1: y=0x01, x=0x02, b=0x04, a=0x08 in byte 3
        data[3] = 0x08  # A
        self.ctrl._parse_standard(data)
        self.assertTrue(self.ctrl.state.a)
        self.assertFalse(self.ctrl.state.b)

        data[3] = 0x04  # B
        self.ctrl._parse_standard(data)
        self.assertTrue(self.ctrl.state.b)

    def test_shoulders_switch1(self):
        data = _base_report(0x30)
        data[3] = 0x40 | 0x80  # R + ZR
        data[5] = 0x40 | 0x80  # L + ZL
        self.ctrl._parse_standard(data)
        self.assertTrue(self.ctrl.state.r)
        self.assertTrue(self.ctrl.state.zr)
        self.assertTrue(self.ctrl.state.l)
        self.assertTrue(self.ctrl.state.zl)

    def test_dpad_switch1(self):
        data = _base_report(0x30)
        data[5] = 0x02  # up
        self.ctrl._parse_standard(data)
        self.assertTrue(self.ctrl.state.dpad_up)
        self.assertFalse(self.ctrl.state.dpad_down)

    def test_battery(self):
        data = _base_report(0x30)
        data[2] = 0x60  # nibble 6
        self.ctrl._parse_standard(data)
        self.assertEqual(self.ctrl.state.battery_level, 6)

    def test_stick_center(self):
        data = _base_report(0x30)
        # Rebuild center sticks carefully
        # left_x = 2048 = 0x800
        data[6] = 0x00
        data[7] = 0x08  # bits 0-3 of high X; bits 4-7 of low Y
        data[8] = 0x80  # high of Y
        # left_y = (0x08 >> 4) | (0x80 << 4) = 0 | 0x800 = 2048 ✓
        data[9] = 0x00
        data[10] = 0x08
        data[11] = 0x80
        self.ctrl._parse_standard(data)
        self.assertEqual(self.ctrl.state.left_stick_x, 2048)
        self.assertEqual(self.ctrl.state.left_stick_y, 2048)


class TestParseStandardSwitch2(unittest.TestCase):
    def setUp(self):
        self.ctrl = SwitchProController()
        self.ctrl.product_id = 0x2069

    def test_face_buttons_switch2_report_09(self):
        data = _base_report(0x09)
        # Switch 2 wired: b=0x01, a=0x02, y=0x04, x=0x08 in byte 3
        data[3] = 0x02  # A
        self.ctrl._parse_standard(data)
        self.assertTrue(self.ctrl.state.a)
        self.assertFalse(self.ctrl.state.b)

        data[3] = 0x01  # B
        self.ctrl._parse_standard(data)
        self.assertTrue(self.ctrl.state.b)
        self.assertFalse(self.ctrl.state.a)

    def test_back_grips(self):
        data = _base_report(0x09)
        data[5] = 0x04 | 0x08  # GR + GL
        self.ctrl._parse_standard(data)
        self.assertTrue(self.ctrl.state.gr)
        self.assertTrue(self.ctrl.state.gz)  # Backward-compatible alias
        self.assertTrue(self.ctrl.state.gl)

    def test_stick_clicks_are_not_c_button(self):
        data = _base_report(0x09)
        data[3] = 0x80  # R3
        data[4] = 0x80  # L3
        data[5] = 0x10  # C, not a stick click
        self.ctrl._parse_standard(data)
        self.assertTrue(self.ctrl.state.l_stick_click)
        self.assertTrue(self.ctrl.state.r_stick_click)
        self.assertTrue(self.ctrl.state.c)
        data[3] = data[4] = 0
        self.ctrl._parse_standard(data)
        self.assertFalse(self.ctrl.state.l_stick_click)
        self.assertFalse(self.ctrl.state.r_stick_click)
        self.assertTrue(self.ctrl.state.c)

    def test_switch2_battery_bits(self):
        data = _base_report(0x09)
        data[2] = 0x24  # battery=9 in bits 2..5, no high nibble match
        self.ctrl._parse_standard(data)
        self.assertEqual(self.ctrl.state.battery_level, 9)


class TestHandleReport(unittest.TestCase):
    def setUp(self):
        self.ctrl = SwitchProController()

    def test_short_data_returns_none(self):
        self.assertIsNone(self.ctrl._handle_report([0x30, 1, 2]))

    def test_unknown_report_returns_none(self):
        data = [0xFF] + [0] * 20
        self.assertIsNone(self.ctrl._handle_report(data))

    def test_standard_report_returns_state(self):
        data = _base_report(0x30)
        state = self.ctrl._handle_report(data)
        self.assertIsInstance(state, ControllerState)

    def test_encode_rumble_neutral(self):
        self.assertEqual(
            SwitchProController._encode_rumble(0, 0),
            [0x00, 0x01, 0x40, 0x40],
        )

    def test_encode_switch2_haptic_zero(self):
        self.assertEqual(
            SwitchProController._encode_switch2_haptic(0),
            [0x00, 0x00, 0x00, 0x00, 0x00],
        )


class TestSimpleReport(unittest.TestCase):
    def test_simple_report_clears_unavailable_buttons(self):
        ctrl = SwitchProController()
        ctrl.state.a = True
        ctrl.state.zl = True
        ctrl._parse_simple([0x3F, 0x00, 0x00, 8] + [0] * 8)
        self.assertFalse(ctrl.state.a)
        self.assertFalse(ctrl.state.zl)

    def test_hat_up(self):
        ctrl = SwitchProController()
        data = [0x3F, 0x00, 0x00, 0] + [0] * 12  # hat = 0 up
        # Need len >= 12 for sticks optional; hat at index 3
        data = [0x3F, 0x00, 0x00, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        ctrl._parse_simple(data)
        self.assertTrue(ctrl.state.dpad_up)
        self.assertFalse(ctrl.state.dpad_down)


if __name__ == "__main__":
    unittest.main()
